# Connecting to a Server

## Example
```
http://example.org/index.html
```
- Scheme: `http`
    - Explains *how* to get the information
- Hostname: `example.org`
    - Explains *where* to get the information
- Path: `/index.html``
    - Explains *what* to get

Browser가 URL로부터 웹 페이지를 다운로드 받으려면?
- Browser -> Hostname으로 지정된 서버에 연결해달라고 OS에 요청
- OS
  - -> DNS에 요청하여 Hostname을 desination IP 주소로 변환
  - -> Routing table을 사용하여 어떤 하드웨어가 통신에 적합한지 결정 (e.g., wireless or wired)
  - -> Device driver를 사용하여 유선/무선으로 신호를 보냄
- 여러 라우터를 거쳐 서버에 도착하면 커넥션이 맺어짐

결론은 브라우저는 Hostname으로 OS에 연결을 요청한다는 사실

# Requesting Information

## HTTP GET 요청 예시

```http request
GET /index.html HTTP/1.0
Host: example.org

```
### 구성
- Method: `GET`
- Path: `/index.html`
- HTTP Version: `HTTP/1.0`
- 각종 헤더
    - Header: `example.org`
    - Value: `Host`
- A single blank line (tells the server that the header is finished)

# The Server's Response

## 응답 예시

```http response
HTTP/1.0 200 OK
...
```

### 구성
- HTTP Version: `HTTP/1.0`
- Response Status Code: `200`
- Response Description: `OK`
- Additional Headers and values

# Telnet in Python

## 단계

- Extracting the host name and path from the URL
- Creating a socket
- Sending a request
- Receiving a response

## Socket의 요소

- Address family
    - 다른 컴퓨터를 어떻게 찾을지?
    - `AF`로 시작. 여기서는 `AF_INET`을 사용할 것. `AF_BLUETOOTH` 같은 것도 존재.
- Type
    - 어떤 종류의 통신을 할 것인지
    - `SOCK`으로 시작. 여기서는 `SOCK_STREAM`을 사용(각 컴퓨터가 임의 크기의 데이터를 보낼 수 있음). `SOCK_DGRAM` 같이 고정 크기를 보내는 방식도 존재.
- Protocol
    - 두 컴퓨터가 커넥션을 맺는 스텝을 설명
    - 여기서는 `IPPROTO_TCP`를 사용

