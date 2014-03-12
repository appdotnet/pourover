import requests

LIST_OF_FEEDS = [
    "http://feeds.feedburner.com/newsyc500",
    "http://feeds2.feedburner.com/TheAwl",
    "http://xkcd.com/rss.xml",
    "http://feeds.feedburner.com/BestOfMetafilter",
    "http://www.wired.com/gadgetlab/author/mathonan/feed/",
    "https://feeds.pinboard.in/rss/u:voidfiles/t:css/",
    "http://pipes.yahoo.com/pipes/pipe.run?_id=d305a04d2f7dc6a87c26ea3b2058d37a&_render=rss&subreddit=all&threshold=4000",
    "http://feeds.dailykos.com/dailykos/index.xml",
    "http://feeds.feedburner.com/Splitsider",
    "http://waxy.org/links/index.xml",
    "http://brooksreview.net/feed",
    "http://www.npr.org/rss/rss.php?id=1001",
    "http://www.npr.org/rss/rss.php?id=100",
    "http://www.npr.org/rss/rss.php?id=1006",
    "http://www.npr.org/rss/rss.php?id=1007",
    "http://www.npr.org/rss/rss.php?id=1057",
    "http://www.npr.org/rss/rss.php?id=1021",
    "http://www.npr.org/rss/rss.php?id=1014",
    "http://www.npr.org/rss/rss.php?id=1003",
    "http://www.npr.org/rss/rss.php?id=1004",
    "http://feeds.sbnation.com/rss/current",
    "http://feeds.sbnation.com/rss/streams/2",
    "http://feeds.sbnation.com/rss/headlines/nascar",
    "http://www.rsssearchhub.com/preview/sbnation-com-mma-storystream-trade-headlines-atom-mJmpmK/",
]


def create_rss_feeds(access_token):

    for feed in LIST_OF_FEEDS:
        print
        print 'Creating %s' % (feed)
        data = {
            'feed_type': 1,
            'feed_url': feed,
            'include_thumb': 'true',
            'include_video': 'true',
            'channel_id': '35921'
        }

        resp = requests.post('https://adn-pourover-staging.appspot.com/api/feeds', data=data, headers={
            'Authorization': 'BEARER %s' % (access_token)
        })
        try:
            resp.raise_for_status()
        except:
            print "Failed to create %s" % (feed)
            print resp.content
            continue
        print "done"
        print resp.json()
        print


def main(access_token):
    create_rss_feeds(access_token)


if __name__ == '__main__':
    import sys
    main(sys.argv[1])
