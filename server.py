import os, logging
from mcp.server.fastmcp import FastMCP
from core import Telegram, stars
logging.basicConfig(level=logging.INFO)
mcp=FastMCP('Telegram Enterprise MCP')
tg=Telegram(os.environ['TELEGRAM_BOT_TOKEN'],os.getenv('TELEGRAM_ALLOWED_CHATS','').split(','),os.getenv('TELEGRAM_ENABLE_WRITES')=='true')
@mcp.tool()
def bot_info(): return tg.call('getMe')
@mcp.tool()
def chat_info(chat_id:str): return tg.call('getChat',locals())
@mcp.tool()
def member_count(chat_id:str): return tg.call('getChatMemberCount',locals())
@mcp.tool()
def administrators(chat_id:str): return tg.call('getChatAdministrators',locals())
@mcp.tool()
def send_message(chat_id:str,text:str,execute:bool=False):
    return tg.call('sendMessage',{'chat_id':chat_id,'text':text},execute)
@mcp.tool()
def publish_paid_media(chat_id:str,file_ids:list[str],price:int,caption:str='',media_type:str='video',execute:bool=False):
    if media_type not in ('photo','video') or not 1<=len(file_ids)<=10: raise ValueError('Invalid media')
    if any('://' in f or not f for f in file_ids): raise ValueError('Use existing Telegram file IDs only')
    return tg.call('sendPaidMedia',{'chat_id':chat_id,'star_count':stars(price),'media':[{'type':media_type,'media':f} for f in file_ids],'caption':caption},execute)
@mcp.tool()
def publish_video(chat_id:str,file_id:str,caption:str='',execute:bool=False):
    if '://' in file_id: raise ValueError('Use Telegram file ID')
    return tg.call('sendVideo',{'chat_id':chat_id,'video':file_id,'caption':caption},execute)
@mcp.tool()
def create_invoice(chat_id:str,title:str,description:str,order_id:str,price:int,execute:bool=False):
    return tg.call('sendInvoice',{'chat_id':chat_id,'title':title,'description':description,'payload':order_id,'currency':'XTR','provider_token':'','prices':[{'label':title,'amount':stars(price)}]},execute)
@mcp.tool()
def star_balance(): return tg.call('getMyStarBalance')
@mcp.tool()
def transactions(offset:int=0,limit:int=50):
    if offset<0 or not 1<=limit<=100: raise ValueError('Invalid pagination')
    return tg.call('getStarTransactions',locals())
@mcp.tool()
def create_invite(chat_id:str,expire_date:int,execute:bool=False):
    return tg.call('createChatInviteLink',{'chat_id':chat_id,'expire_date':expire_date,'member_limit':1},execute)
@mcp.tool()
def refund(user_id:int,charge_id:str,execute:bool=False):
    if os.getenv('TELEGRAM_ENABLE_REFUNDS')!='true': raise ValueError('Refunds disabled')
    return tg.call('refundStarPayment',{'user_id':user_id,'telegram_payment_charge_id':charge_id},execute)
@mcp.tool()
def pin_message(chat_id:str,message_id:int,execute:bool=False):
    return tg.call('pinChatMessage',{'chat_id':chat_id,'message_id':message_id},execute)
@mcp.tool()
def edit_message(chat_id:str,message_id:int,text:str,execute:bool=False):
    return tg.call('editMessageText',{'chat_id':chat_id,'message_id':message_id,'text':text},execute)
if __name__=='__main__': mcp.run(transport='stdio')
