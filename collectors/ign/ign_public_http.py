"""Small public-HTTP adapter shared by IGN collectors; no browser credentials."""
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


class PublicResponse:
    def __init__(self, response):
        if hasattr(response, 'status_code'):
            self.status = response.status_code
            self.url = str(response.url)
            self.body = response.content
            return
        self.status = response.code
        self.url = response.geturl()
        self.body = response.read()

    def text(self):
        return self.body.decode('utf-8-sig', errors='replace')

    def json(self):
        return json.loads(self.text())


class PublicHTTP:
    def __init__(self, proxy=None, persistent=True):
        self.opener = build_opener(ProxyHandler({'http': proxy, 'https': proxy}) if proxy else ProxyHandler())
        self.client = None
        self.network_errors = (URLError, ConnectionError, TimeoutError, OSError)
        if not persistent:
            return
        try:
            import httpx
        except ImportError:
            return
        self.client = httpx.Client(proxy=proxy, timeout=45, follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=2, keepalive_expiry=60))
        self.network_errors += (httpx.TransportError,)

    def get(self, url, headers=None, timeout=45000):
        for attempt in range(3):
            try:
                if self.client:
                    return PublicResponse(self.client.get(url, timeout=timeout/1000,
                        headers={'User-Agent': 'GameCatalogCollector/0.3 (+public HTML collection)', **(headers or {})}))
                request = Request(url, headers={'User-Agent': 'GameCatalogCollector/0.3 (+public HTML collection)', **(headers or {})})
                try:
                    response = self.opener.open(request, timeout=timeout/1000)
                except HTTPError as exc:
                    response = exc
                with response:
                    return PublicResponse(response)
            except self.network_errors:
                if attempt == 2:
                    raise
                time.sleep(4 * (attempt + 1))

    def dispose(self):
        if self.client:
            self.client.close()
