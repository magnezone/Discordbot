# Discordbot
discordを使ったYoutubeのライブ配信通知bot

## 実行環境
python=3.7

## 注意点
本プログラムはYouTube Data APIを使用します．利用前にGoogle Cloud Platformの登録をしてください．

## 使い方
1. oauth2.0クライアント認証のためのclient_secrets.jsonをmain.pyと同じディレクトリに配置し，次の行を書き換えてください．
    - 19行目：自分のYouTubeチャンネルID
    - 20行目：Discord botのトークン
1. main.pyを実行