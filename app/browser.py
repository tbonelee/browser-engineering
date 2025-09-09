import socket
import ssl
import sys
import time
import gzip

connections = {}

# Simple in-memory caches
# Key is full URL (origin + path)
_response_cache = {}  # key -> {"expires_at": float|None, "body": str}
_redirect_cache = {}  # key -> {"expires_at": float|None, "location": str}


def _cache_is_valid(entry):
    if not entry:
        return False
    expires_at = entry.get("expires_at")
    if expires_at is None:
        return True
    return time.time() <= expires_at


def _parse_cache_control(header_value):
    """Parse Cache-Control and decide cacheability and max-age.

    Returns (cacheable: bool, max_age_seconds: int|None).
    Only supports 'no-store' and 'max-age'. Any other directive disables caching.
    """
    if not header_value:
        return True, None

    tokens = [t.strip() for t in header_value.split(",") if t.strip()]
    max_age = None
    for token in tokens:
        token_l = token.casefold()
        if token_l == "no-store":
            return False, None
        elif token_l.startswith("max-age="):
            try:
                max_age = int(token_l.split("=", 1)[1])
            except Exception:
                return False, None
        else:
            # Unknown directive → do not cache
            return False, None
    return True, max_age


class URL:
    def __init__(self, url):
        if url.startswith("view-source:"):
            url = url[len("view-source:") :]
            self.view_source = True
        else:
            self.view_source = False

        if url.startswith("data:"):
            self.scheme, url = url.split(":", 1)
        else:
            self.scheme, url = url.split("://", 1)
        assert self.scheme in ["http", "https", "file", "data"]
        if self.scheme == "file" or self.scheme == "data":
            self.host = None
            self.port = None
            self.path = url
            return

        if self.scheme == "http":
            self.port = 80
        elif self.scheme == "https":
            self.port = 443
        if "/" not in url:
            url = url + "/"  # Add trailing slash if missing
        self.host, url = url.split("/", 1)
        if ":" in self.host:
            self.host, port = self.host.split(":", 1)
            self.port = int(port)
        self.path = "/" + url

    def _request_file(self):
        assert self.scheme == "file"
        if not self.path:
            self.path = "./test.html"  # For development
        with open(self.path, "r", encoding="utf8") as f:
            return f.read()

    def _request_data(self):
        assert self.scheme == "data"
        mediatype, data = self.path.split(",", 1)
        # TODO: handle mediatype
        # TODO: base64 handling
        return data

    def get_origin(self):
        return self.scheme + "://" + self.host + ":" + str(self.port)

    def request(self):
        if self.scheme == "file":
            return self._request_file()
        elif self.scheme == "data":
            return self._request_data()
        # Build cache key
        cache_key = self.get_origin() + self.path

        # Check redirect cache first
        redirect_entry = _redirect_cache.get(cache_key)
        if _cache_is_valid(redirect_entry):
            return URL(redirect_entry["location"]).request()

        # Check response cache
        response_entry = _response_cache.get(cache_key)
        if _cache_is_valid(response_entry):
            return response_entry["body"]
        connection_cache = connections.get(self.get_origin())
        if connection_cache:
            s = connection_cache
        else:
            s = socket.socket(
                family=socket.AF_INET,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )
            s.connect((self.host, self.port))
            if self.scheme == "https":
                ctx = ssl.create_default_context()
                s = ctx.wrap_socket(s, server_hostname=self.host)

        connections[self.get_origin()] = s  # For keep-alive

        request = "GET {} HTTP/1.1\r\n".format(self.path)
        request += "Host: {}\r\n".format(self.host)
        request += "Connection: Keep-Alive\r\n"
        request += "User-Agent: Python-Browser\r\n"
        request += "Accept-Encoding: gzip\r\n"
        request += "\r\n"
        s.send(request.encode("utf8"))

        response = s.makefile("rb", newline="\r\n")

        statusline = response.readline()
        version, status, explanation = statusline.decode("utf8").split(" ", 2)
        status_code = int(status)

        response_headers = {}
        while True:
            line = response.readline().decode("utf8")
            if line == "\r\n":
                break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()

        # Helpers
        def _read_chunked_body(fobj):
            body_bytes = b""
            while True:
                size_line = fobj.readline().decode("utf8")
                # Handle optional chunk extensions after ';'
                size_token = size_line.split(";", 1)[0].strip()
                if not size_token:
                    continue
                size = int(size_token, 16)
                if size == 0:
                    # Consume optional trailer headers until blank line or EOF
                    while True:
                        trailer_line = fobj.readline().decode("utf8")
                        if not trailer_line:  # EOF guard
                            break
                        if trailer_line == "\r\n":
                            break
                    break
                chunk = fobj.read(size)
                body_bytes += chunk
                # Consume trailing CRLF after each chunk
                _ = fobj.read(2)
            return body_bytes

        if 300 <= status_code < 400:
            location = response_headers["location"]
            if location.startswith("/"):
                location = self.get_origin() + location

            # Cache permanent redirect (301) if allowed
            if status_code == 301:
                cache_control = response_headers.get("cache-control")
                cacheable, max_age = _parse_cache_control(cache_control)
                if cacheable:
                    expires_at = time.time() + max_age if max_age is not None else None
                    _redirect_cache[cache_key] = {
                        "expires_at": expires_at,
                        "location": location,
                    }

            return URL(location).request()

        # Read body according to Transfer-Encoding / Content-Length
        transfer_encoding = response_headers.get("transfer-encoding")
        if transfer_encoding:
            encodings = [
                e.strip().casefold() for e in transfer_encoding.split(",") if e.strip()
            ]
            assert all(
                c == "chunked" for c in encodings
            ), f"Unsupported Transfer-Encoding: {transfer_encoding}"
            body_bytes = _read_chunked_body(response)
        else:
            # No transfer-encoding; rely on Content-Length
            content_length = int(response_headers["content-length"])
            body_bytes = response.read(content_length)

        # Apply content-encoding (only gzip supported)
        content_encoding = response_headers.get("content-encoding", "").casefold()
        if content_encoding:
            encodings = [e.strip() for e in content_encoding.split(",") if e.strip()]
            assert all(
                c == "gzip" for c in encodings
            ), f"Unsupported Content-Encoding: {content_encoding}"
            for _ in encodings:
                body_bytes = gzip.decompress(body_bytes)

        # Decode to text for display/caching
        content = body_bytes.decode("utf8", errors="replace")

        # Cache 200 and 404 responses if allowed by Cache-Control
        if status_code in (200, 404):
            cache_control = response_headers.get("cache-control")
            cacheable, max_age = _parse_cache_control(cache_control)
            if cacheable:
                expires_at = time.time() + max_age if max_age is not None else None
                _response_cache[cache_key] = {"expires_at": expires_at, "body": content}

        return content


def show(body, view_source=False):
    """
    Prints the body without tags
    :param body:
    :return:
    """
    if view_source:
        print(body)
        return

    in_tag = False
    i = 0
    while i < len(body):
        c = body[i]
        if c == "&":
            candid = body[i + 0 : i + 4]
            if candid == "&gt;":
                print(">", end="")
                i += 4
                continue
            elif candid == "&lt;":
                print("<", end="")
                i += 4
                continue

        if c == "<":
            in_tag = True
        elif c == ">":
            in_tag = False
        elif not in_tag:
            print(c, end="")
        i += 1


def load(url: URL):
    body = url.request()
    show(body, url.view_source)


if __name__ == "__main__":
    # load(URL(sys.argv[1]))
    load(URL("http://browser.engineering/redirect3"))
