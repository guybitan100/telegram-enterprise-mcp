import os, json, logging
import httpx

READ = {'getMe','getChat','getChatMemberCount','getChatAdministrators','getMyStarBalance','getStarTransactions'}
class Telegram:
    def __init__(self, token, chats, live=False, client=None):
        self.token=token; self.chats={str(c) for c in chats}; self.live=live
        self.client=client or httpx.Client(timeout=30, follow_redirects=False)
    def call(self, method, payload=None, execute=False):
        p=payload or {}
        if 'chat_id' in p and str(p['chat_id']) not in self.chats:
            raise ValueError('Chat not allowlisted')
        if method not in READ and not (self.live and execute):
            return {'dry_run':True,'method':method,'payload':p}
        try:
            r=self.client.post(f'https://api.telegram.org/bot{self.token}/{method}',json=p)
            data=r.json()
        except (httpx.HTTPError, ValueError):
            raise RuntimeError('Telegram transport failure; write outcome may be unknown') from None
        if not r.is_success or not data.get('ok'):
            raise RuntimeError(f'Telegram rejected request ({r.status_code}); retry_after={data.get("parameters",{}).get("retry_after")}')
        logging.getLogger('audit').info('method=%s chat=%s status=success',method,p.get('chat_id','-'))
        return data['result']

def stars(n):
    if not 1<=n<=25000: raise ValueError('Stars must be 1..25000')
    return n
