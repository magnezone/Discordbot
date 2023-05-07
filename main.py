import discord
from discord.ext import tasks
import feedparser
import httplib2
import os
from googleapiclient.discovery import build
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import argparser, run_flow
import json
import sys
from bs4 import BeautifulSoup
import re
import aiohttp

with open(__file__+"/../token.json") as f:
    #Use your Discord bot token
    a = json.load(f)
    YOUR_CHANNEL_ID = a["CHANNEL_ID"]
    TOKEN = a["TOKEN"]

# The CLIENT_SECRETS_FILE variable specifies the name of a file that contains
# the OAuth 2.0 information for this application, including its client_id and
# client_secret. You can acquire an OAuth 2.0 client ID and client secret from
# the Google API Console at
# https://console.developers.google.com/.
# Please ensure that you have enabled the YouTube Data API for your project.
# For more information about using OAuth2 to access the YouTube Data API, see:
#   https://developers.google.com/youtube/v3/guides/authentication
# For more information about the client_secrets.json file format, see:
#   https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
CLIENT_SECRETS_FILE = __file__+"/../"+"client_secrets.json"

# This OAuth 2.0 access scope allows for full read/write access to the
# authenticated user's account.
YOUTUBE_READ_WRITE_SCOPE = "https://www.googleapis.com/auth/youtube"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

# This variable defines a message to display if the CLIENT_SECRETS_FILE is
# missing.
MISSING_CLIENT_SECRETS_MESSAGE = """
WARNING: Please configure OAuth 2.0

To make this sample run you will need to populate the client_secrets.json file
found at:

    %s

with information from the API Console
https://console.developers.google.com/

For more information about the client_secrets.json file format, please visit:
https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
""" % os.path.abspath(os.path.join(os.path.dirname(__file__),CLIENT_SECRETS_FILE))

def get_authenticated_service(args):
    flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE,scope=YOUTUBE_READ_WRITE_SCOPE,message=MISSING_CLIENT_SECRETS_MESSAGE)
    storage = Storage("%s-oauth2.json" % sys.argv[0])
    credentials = storage.get()

    if credentials is None or credentials.invalid:
        run_flow(flow, storage, args)
    print(credentials.authorize(httplib2.Http()))
    return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,http=credentials.authorize(httplib2.Http()))

argparser.add_argument("--channel-id", help="ID of the channel to subscribe to.",default=YOUR_CHANNEL_ID)
args = argparser.parse_args()
youtube = get_authenticated_service(args)

#---------------------------------------------------------
#intents = discord.Intents(messages=True, guilds=True,message_content=True)
client = discord.Client()
queue = []
my_subs_channels = []
status = True

#自分の登録チャンネルのリストを返却する
def getMySubsChannels():
    global youtube
    #youtube_apiでsubscriptionsのlistを取得
    channels = youtube.subscriptions().list(
      part="snippet",
      #Use your channel id.
      channelId=YOUR_CHANNEL_ID,
      maxResults=50
      ).execute()
    #channelIdを保存する変数
    channelIds = []
    #channelIdsにすべてのchannelIdを保存
    for channel in channels["items"]:
      id = channel["snippet"]["resourceId"]["channelId"]
      channelIds.append(id)
    print("channelIds:",channelIds)
    return channelIds

#最新の動画のvideoIdを取得する
def getLatestVideoIds(channelIds:list):
    #末尾にchannelIdを結合する
    videoIds = []
    for channelId in channelIds:
        youtube_rss_url = "https://www.youtube.com/feeds/videos.xml?channel_id="
        parser = feedparser.parse(youtube_rss_url+channelId)
        videoIds.append(parser["entries"][0]["yt_videoid"])
    print("videoIds:",videoIds)
    return videoIds

#APIを使ってビデオIDのリストから生放送中の動画のビデオIDのリストを取得する．
def getLiveStreamingsIdsFromApi(videoIds:list):
    global youtube
    liveStreamings = []
    for videoid in videoIds:
      liveStreaming = youtube.videos().list(
          part = "snippet",
          id=videoid
      ).execute()
      for video in liveStreaming["items"]:
        if(video["snippet"]["liveBroadcastContent"] == "live"):
            liveStreamings.append(videoid)
    print("liveStreamings:",liveStreamings)
    return liveStreamings

#ビデオIDのリストから生放送中の動画のビデオIDのリストを取得する．
async def getLiveStreamingsIds(videoIds:list):
    global youtube
    liveStreamings = []
    videoURL = "https://www.youtube.com/watch?v="
    async with aiohttp.ClientSession() as session:
        for videoId in videoIds:
            async with session.get(videoURL+videoId) as res:
                soup = BeautifulSoup(await res.text(),"html.parser")
                js_var = "ytInitialPlayerResponse"
                script = soup.find('script', string=re.compile(js_var, re.DOTALL))
                regex = '(?:var ' + js_var + ' = )({.*?})(?:;)'
                json_str = re.search(regex, script.string).group(1)
                a = json.loads(json_str)
                try:
                    print(a["microformat"]["playerMicroformatRenderer"]["liveBroadcastDetails"]["isLiveNow"])
                    if(a["microformat"]["playerMicroformatRenderer"]["liveBroadcastDetails"]["isLiveNow"] == True):
                        liveStreamings.append(videoId)
                except:
                    pass
    print("liveStreamings:",liveStreamings)
    return liveStreamings

#全てのテキストチャンネルを取得
def getTextChannels():
    TextChannels = []
    for channel in client.get_all_channels():
        if(type(channel) == discord.channel.TextChannel):
            TextChannels.append(channel)
    print("TextChannels:",TextChannels)
    return TextChannels

#引数のテキストチャンネルに生放送のurlを送信する
async def noticeLiveStreaming(textChannels:list):
    global queue,my_subs_channels
    YOUTUBE_URL = "https://www.youtube.com/watch?v="
    latestVideoIds = getLatestVideoIds(my_subs_channels)
    liveStreamingIds = await getLiveStreamingsIds(latestVideoIds)
    for liveStreamingId in liveStreamingIds:
        if liveStreamingId not in queue:
            for textChannel in textChannels:
                videoUrl = YOUTUBE_URL+liveStreamingId
                await textChannel.send(videoUrl)
    queue = liveStreamingIds

#引数のテキストチャンネルに生放送のurlを送信する
#過去の通知に関わらず全ての配信を通知する
async def noticeNowLiveStreaming(textChannels:list):
    global queue,my_subs_channels
    YOUTUBE_URL = "https://www.youtube.com/watch?v="
    latestVideoIds = getLatestVideoIds(my_subs_channels)
    liveStreamingIds = await getLiveStreamingsIds(latestVideoIds)
    for liveStreamingId in liveStreamingIds:
        for textChannel in textChannels:
            videoUrl = YOUTUBE_URL+liveStreamingId
            await textChannel.send(videoUrl)
    if(liveStreamingIds == []):
        for textChannel in textChannels:
            await textChannel.send("None")
    queue = liveStreamingIds

@tasks.loop(minutes=1)
async def Loop(textChannels:list):
    await noticeLiveStreaming(textChannels)

@client.event
async def on_ready():
    global my_subs_channels
    # 起動したらターミナルにログイン通知が表示される
    print('ログインしました')
    textChannels = getTextChannels()
    for textChannel in textChannels:
        await textChannel.send("ログインしました")
    Loop.start(textChannels)

# メッセージ受信時に動作する処理
@client.event
async def on_message(message):
    global status,my_subs_channels
    print("message",message)
    # メッセージ送信者がBotだった場合は無視する
    if message.author.bot:
        return
    # 「/neko」と発言したら「にゃーん」が返る処理
    if message.content in ['/neko',"/ねこ"]:
        print("neko")
        await message.channel.send('にゃーん')
    if message.content in ["/help","/ヘルプ"]:
        await message.channel.send("/neko /ねこ:にゃーん \n\
                                    /live:配信中チャンネルを表示 \n\
                                    /status:botの状態を表示 \n\
                                    /disable:botを無効化 \n\
                                    /enable:botを有効化 \n\
                                    /update:登録チャンネルを更新する ")
    if message.content in ["/live"]:
        await noticeNowLiveStreaming([message.channel])
    if message.content in ["/status"]:
        await message.channel.send(status)
    if message.content in ["/disable"]:
        status = False
        await message.channel.send("わたくしを無効化するなんて...")
    if message.content in ["/enable"]:
        status = True
        await message.channel.send("有効化しました！")
    if message.content in ["/update"]:
        my_subs_channels = getMySubsChannels()
        await message.channel.send("登録チャンネルを更新しました！")

# Botの起動とDiscordサーバーへの接続
client.run(TOKEN)