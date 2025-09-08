import socket
import ssl
import sys

connections = {}


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
        request += "\r\n"
        s.send(request.encode("utf8"))

        response = s.makefile("rb", newline="\r\n")

        statusline = response.readline()
        version, status, explanation = statusline.decode("utf8").split(" ", 2)

        response_headers = {}
        while True:
            line = response.readline().decode("utf8")
            if line == "\r\n":
                break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()

        # 다음 두 헤더는 일단 허용하지 않도록
        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers

        content_length = int(response_headers["content-length"])
        content = response.read(content_length).decode("utf8")
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
    load(URL(sys.argv[1]))
