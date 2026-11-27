import httpx, pytest
from core import Telegram, stars

def test_dry_run():
    t=Telegram('secret',['@a'])
    assert t.call('sendMessage',{'chat_id':'@a'},True)['dry_run']
def test_allowlist():
    with pytest.raises(ValueError): Telegram('x',['@a']).call('getChat',{'chat_id':'@b'})
def test_explicit_execute():
    assert Telegram('x',['@a'],True).call('sendMessage',{'chat_id':'@a'})['dry_run']
def test_live():
    c=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'ok':True,'result':42})))
    assert Telegram('x',['@a'],True,c).call('sendMessage',{'chat_id':'@a'},True)==42
def test_secret_redaction():
    c=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(400,json={'ok':False,'description':'secret'})))
    with pytest.raises(RuntimeError,match='Telegram rejected') as e: Telegram('secret',[],False,c).call('getMe')
    assert 'secret' not in str(e.value)
@pytest.mark.parametrize('n',[0,25001,-1])
def test_invalid_stars(n):
    with pytest.raises(ValueError): stars(n)
