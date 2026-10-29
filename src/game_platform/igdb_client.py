"""Rate-limited IGDB client. Tokens stay in memory; HTTP errors are sanitized."""
import time
import httpx


class APIError(RuntimeError):
    pass


class IGDBClient:
    def __init__(self, client_id, client_secret, http=None, interval=0.35, retries=3):
        self.client_id = client_id
        self.client_secret = client_secret
        self.http = http or httpx.Client(timeout=45)
        self.owns_http = http is None
        self.interval = interval
        self.retries = retries
        self.token = None
        self.next_request = 0

    def __enter__(self):
        self.authenticate()
        return self

    def __exit__(self, *_):
        if self.owns_http:
            self.http.close()

    def authenticate(self):
        try:
            response = self.http.post('https://id.twitch.tv/oauth2/token', data={
                'client_id': self.client_id, 'client_secret': self.client_secret,
                'grant_type': 'client_credentials'})
        except httpx.HTTPError as exc:
            raise APIError('Twitch 认证网络请求失败，请检查网络。') from None
        if response.status_code != 200:
            raise APIError(f'Twitch 认证失败（HTTP {response.status_code}），请检查本地 Client ID / Client Secret。')
        try:
            self.token = response.json()['access_token']
        except (ValueError, KeyError):
            raise APIError('Twitch 认证响应格式异常。') from None
        try:
            validation = self.http.get('https://id.twitch.tv/oauth2/validate', headers={'Authorization': 'OAuth '+self.token})
        except httpx.HTTPError:
            raise APIError('Twitch token 验证网络请求失败。') from None
        if validation.status_code != 200 or validation.json().get('client_id') != self.client_id:
            raise APIError('Twitch token 验证失败。')

    def query(self, endpoint, body):
        if endpoint not in {'games', 'games/count', 'game_types'}:
            raise ValueError('Unsupported endpoint')
        renewed = False
        for attempt in range(self.retries+1):
            time.sleep(max(0, self.next_request-time.monotonic()))
            self.next_request = time.monotonic()+self.interval
            try:
                response = self.http.post('https://api.igdb.com/v4/'+endpoint,
                    headers={'Client-ID': self.client_id, 'Authorization': 'Bearer '+self.token,
                             'Accept': 'application/json', 'Content-Type': 'text/plain'}, content=body)
            except httpx.HTTPError:
                if attempt == self.retries:
                    raise APIError('IGDB 网络请求连续失败，已保留采集进度。') from None
                time.sleep(min(20, 2**(attempt+1)))
                continue
            if response.status_code == 401 and not renewed:
                self.authenticate(); renewed = True
                continue
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt == self.retries:
                    raise APIError(f'IGDB 暂停采集（HTTP {response.status_code}），稍后重跑可恢复。')
                try:
                    wait = float(response.headers.get('Retry-After', 2**(attempt+1)))
                except ValueError:
                    wait = 2**(attempt+1)
                if wait > 60:
                    raise APIError('IGDB 要求等待超过一分钟，请稍后重跑，进度已保留。')
                time.sleep(max(1, wait))
                continue
            if response.status_code != 200:
                raise APIError(f'IGDB 返回 HTTP {response.status_code}。查询内容会保存在失败报告中，不包含凭据。')
            try:
                return response.json()
            except ValueError:
                raise APIError('IGDB 返回非 JSON 内容。') from None
        raise APIError('认证重试后仍未成功，采集进度已保留。')
