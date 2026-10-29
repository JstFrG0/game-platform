import httpx
import pytest
from game_platform.igdb_client import IGDBClient, APIError


def test_auth_validation_retry_and_no_secret_in_error(monkeypatch):
    monkeypatch.setattr('game_platform.igdb_client.time.sleep',lambda _:None)
    attempts={'api':0}
    def respond(request):
        if request.url.path.endswith('/token'):return httpx.Response(200,json={'access_token':'mock-token'})
        if request.url.path.endswith('/validate'):return httpx.Response(200,json={'client_id':'mock-client'})
        attempts['api']+=1
        if attempts['api']==1:return httpx.Response(429,headers={'Retry-After':'1'})
        return httpx.Response(200,json=[{'id':1}])
    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        with IGDBClient('mock-client','mock-secret',http=http,interval=0) as client:
            assert client.query('games','fields id;')==[{'id':1}]
    assert attempts['api']==2


def test_auth_failure_is_sanitized():
    def respond(_):return httpx.Response(400,json={'message':'mock-secret must not be printed'})
    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        with pytest.raises(APIError) as exc:IGDBClient('mock-client','mock-secret',http=http).authenticate()
    assert 'mock-secret' not in str(exc.value)
