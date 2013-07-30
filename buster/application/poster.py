from collections import defaultdict
import logging
from lxml import html
import json
import StringIO
from urlparse import urlparse
import urllib


from bs4 import BeautifulSoup
from fnl.nlp import sentencesplitter as splitter
from google.appengine.ext import ndb
from constants import FORMAT_MODE
from django.utils.encoding import iri_to_uri
from utils import (append_query_string, strip_html_tags, ellipse_text, get_language,
                   guid_for_item)


logger = logging.getLogger(__name__)

MAX_CHARS = 256


def parse_style_tag(text):
    if not text:
        return text
    text = text.strip()
    attrs = text.split(';')
    attrs = filter(None, map(lambda x: x.strip(), attrs))
    attrs = map(lambda x: x.split(':'), attrs)
    # logger.info('attrs: %s', attrs)
    return {x[0].strip(): x[1].strip() for x in attrs}


def find_video_src_url(item):
    summary = item.get('summary', item.get('content'))
    if not summary:
        return None, None

    soup = BeautifulSoup(summary)

    possible_embeds = soup.findAll('iframe')
    possible_embeds += soup.findAll('embed')

    for embed in possible_embeds:
        src_url = embed.get('src')
        urlparts = urlparse(src_url)
        if urlparts.netloc.endswith('youtube.com'):
            return src_url, 'youtube'

        if urlparts.netloc.endswith('vimeo.com'):
            return src_url, 'vimeo'

    return None, None


# http://stackoverflow.com/questions/4356538/how-can-i-extract-video-id-from-youtubes-link-in-python
def normalize_youtube_link(url):
    """
    Examples:
    - http://youtu.be/SA2iWivDJiE
    - http://www.youtube.com/watch?v=_oPAwA_Udwc&feature=feedu
    - http://www.youtube.com/embed/SA2iWivDJiE
    - http://www.youtube.com/v/SA2iWivDJiE?version=3&amp;hl=en_US
    """
    video_id = None
    query = urlparse(url)
    if query.hostname == 'youtu.be':
        video_id = query.path[1:]
    if query.hostname in ('www.youtube.com', 'youtube.com'):
        if query.path == '/watch':
            p = parse_qs(query.query)
            video_id = p['v'][0]
        if query.path[:7] == '/embed/':
            video_id = query.path.split('/')[2]
        if query.path[:3] == '/v/':
            video_id = query.path.split('/')[2]
    # fail?
    return 'http://www.youtube.com/watch?v=%s' % (video_id)


OEMBED_ENDPOINTS = {
    'vimeo': 'http://vimeo.com/api/oembed.json',
    'youtube': 'http://www.youtube.com/oembed',
}


@ndb.tasklet
def find_video_oembed(item):
    url, oembed_provider = find_video_src_url(item)
    if not url or not oembed_provider:
        return

    if url.startswith('//'):
        url = 'http:' + url

    if oembed_provider == 'youtube':
        url = normalize_youtube_link(url)

    if not url:
        return

    params = {
        'url': url
    }

    query_string = urllib.urlencode(params)
    ctx = ndb.get_context()
    resp = yield ctx.urlfetch(url='%s?%s' % (OEMBED_ENDPOINTS[oembed_provider], query_string), method='GET')
    # logger.info('Trying to fetch oembed data url:%s status_code:%s', url, resp.status_code)
    if resp.status_code != 200:
        raise ndb.Return(None)
    # logger.info('Found video provider:%s url:%s embed:%s', oembed_provider, url, json.loads(resp.content))
    raise ndb.Return(json.loads(resp.content))


def build_html_from_post(post):

    def entity_text(e):
        return post['text'][e['pos']:e['pos'] + e['len']]

    link_builder = lambda l: "<a href='%s'>%s</a>" % (l['url'], entity_text(l))

    # map starting position, length of entity placeholder to the replacement html
    entity_map = {}
    for entity_key, builder in [('links', link_builder)]:
        for entity in post.get('entities', {}).get(entity_key, []):
            entity_map[(entity['pos'], entity['len'])] = builder(entity)

    # replace strings with html
    html_pieces = []
    text_idx = 0  # our current place in the original text string
    for entity_start, entity_len in sorted(entity_map.keys()):
        if text_idx != entity_start:
            # if our current place isn't the start of an entity, bring in text until the next entity
            html_pieces.append(post.get('text', "")[text_idx:entity_start])

        # pull out the entity html
        entity_html = entity_map[(entity_start, entity_len)]
        html_pieces.append(entity_html)

        # move past the entity we just added
        text_idx = entity_start + entity_len

    # clean up any remaining text
    html_pieces.append(post.get('text', "")[text_idx:])
    html = ''.join(html_pieces)
    html = html.replace('\n', '<br>')
    # TODO: link to schema
    return '<span>%s</span>' % (html)


def get_link_for_item(feed, item):
    feed_link = feed.feed_url
    main_item_link = item.get('link')

    # If the user hasn't turned on linked list mode
    # return the main_item_link
    if not feed.linked_list_mode:
        return main_item_link

    # if the feed is so malformed it doesn't link to it's self then
    # just return the main item link
    if not feed_link:
        return main_item_link

    parsed_feed_link = urlparse(feed_link)
    parsed_item_link = urlparse(main_item_link)

    # If the main link has the same root domain as the feed
    # This is linking back to the blog already so return
    # The main link.
    if parsed_feed_link.netloc == parsed_item_link.netloc:
        return main_item_link

    # If we are still here, we should now look through the alternate links
    links = item.get('links', [])
    for link in links:
        href = link.get('href')
        if not href:
            continue

        parsed_link = urlparse(href)
        # If we find an alternate link that matches domains
        # we make the assumption that this is the permalink back to the blog
        if parsed_link.netloc == parsed_feed_link.netloc:
            return href

    # If we are still here we now need to look through the links that are in the content
    soup = BeautifulSoup(item.get('summary', ''))
    links = soup.findAll('a')

    # No links, then we are out of look return the main_item_link
    if not links:
        return main_item_link

    # Right now lets just try this on the last link
    last_link = links[-1]
    # logger.info('Last link: %s', last_link)
    href = last_link.get('href')
    parsed_link = urlparse(href)
    # logger.info('Last link parsed: %s %s %s', parsed_link.netloc, parsed_feed_link.netloc, parsed_link)
    # If the domains match lets use this as the URL
    if parsed_link.netloc == parsed_feed_link.netloc:
        return href

    # Finally lets try a last ditch custom method
    # we can just ask the user to change up their content so we can find something in it
    permalink = soup.find('a', {'rel': 'permalink'})
    if permalink:
        href = permalink.get('href')
        if href:
            return href

    return main_item_link


def find_thumbnail(item):
    min_d = 200
    max_d = 1000
    media_thumbnails = item.get('media_thumbnail') or []
    for thumb in media_thumbnails:
        w = int(thumb.get('width', 0))
        h = int(thumb.get('height', 0))
        if all([w, h, w >= min_d, w <= max_d, h >= min_d, w <= max_d]):
            return {
                'thumbnail_image_url': thumb['url'],
                'thumbnail_image_width': int(thumb['width']),
                'thumbnail_image_height': int(thumb['height'])
            }

    soup = BeautifulSoup(item.get('summary', ''))
    for image in soup.findAll('img'):
        w = image.get('width', 0)
        h = image.get('height', 0)
        if not (w and h):
            style = parse_style_tag(image.get('style'))
            if style:
                w = style.get('width', w)
                h = style.get('height', h)

        if not(w and h):
            continue

        w, h = map(lambda x: x.replace('px', ''), (w, h))

        try:
            w = int(w)
            h = int(h)
        except:
            continue

        if all([w, h, w >= min_d, w <= max_d, h >= min_d, w <= max_d]):
            return {
                'thumbnail_image_url': image['src'],
                'thumbnail_image_width': w,
                'thumbnail_image_height': h,
            }

    return None


@ndb.tasklet
def get_meta_data_for_url(url):
    ctx = ndb.get_context()

    try:
        resp = yield ctx.urlfetch(url=url, deadline=60, follow_redirects=True)
    except Exception:
        logger.exception('Failed to fetch meta data for %s' % url)
        raise ndb.Return({})

    doc = html.parse(StringIO.StringIO(resp.content))
    data = defaultdict(dict)
    props = doc.xpath('//meta[re:test(@name|@property, "^twitter|og:.*$", "i")]',
                      namespaces={"re": "http://exslt.org/regular-expressions"})

    for prop in props:
        if prop.get('property'):
            key = prop.get('property').split(':')
        else:
            key = prop.get('name').split(':')

        if prop.get('content'):
            value = prop.get('content')
        else:
            value = prop.get('value')

        if not value:
            continue
        value = value.strip()

        if value.isdigit():
            value = int(value)

        ref = data[key.pop(0)]

        for idx, part in enumerate(key):
            if not key[idx:-1]: # no next values
                ref[part] = value
                break
            if not ref.get(part):
                ref[part] = dict()
            else:
                if isinstance(ref.get(part), basestring):
                    ref[part] = {'url': ref[part]}
            ref = ref[part]
    logger.info('Found some meta data: %s', data)
    raise ndb.Return(data)


@ndb.tasklet
def get_short_url(entry, link, feed):
    if entry.short_url:
        raise ndb.Return(entry.short_url)

    params = {
        'login': feed.bitly_login,
        'apiKey': feed.bitly_api_key,
        'longUrl': link,
    }

    ctx = ndb.get_context()
    query_string = urllib.urlencode(params)
    resp = yield ctx.urlfetch(url='https://api-ssl.bitly.com/v3/shorten?%s' % (query_string), method='GET')
    if resp.status_code == 200:
        logger.info('url: %s Resp content: %s', 'https://api-ssl.bitly.com/v3/shorten?%s' % (query_string), resp.content)
        resp_json = json.loads(resp.content)
        if resp_json['status_code'] == 200:
            link = resp_json['data']['url']
            entry.short_url = link
            yield entry.put_async()
            raise ndb.Return(link)


@ndb.tasklet
def prepare_entry_from_item(rss_feed, item, feed, overflow=False, overflow_reason=None, published=False):
    title_detail = item.get('title_detail')
    title = item.get('title', 'No Title')

    # If the title is HTML then we need to decode it to some kind of usable text
    # Definitely need to decode any entities
    if title_detail:
        if title_detail['type'] == u'text/html':
            title = BeautifulSoup(title).text

    link = iri_to_uri(get_link_for_item(feed, item))

    # We can only store a title up to 500 chars
    title = title[0:499]
    guid = guid_for_item(item)
    if len(guid) > 500:
        logger.warn('Found a guid > 500 chars link: %s item: %s', guid, item)
        return

    if not link:
        logger.warn("Item found without link skipping item: %s", item)
        return

    if len(link) > 500:
        logger.warn('Found a link > 500 chars link: %s item: %s', link, item)
        return

    if not guid:
        logger.warn("Item found without guid skipping item: %s", item)
        return

    summary = item.get('summary', '')
    kwargs = dict(guid=guid, title=title, summary=summary, link=link,
                  published=published, overflow=overflow, overflow_reason=overflow_reason)

    if feed:
        kwargs['parent'] = feed.key

    try:
        thumbnail = find_thumbnail(item)
        if thumbnail:
            kwargs.update(thumbnail)
    except Exception, e:
        logger.info("Exception while trying to find thumbnail %s", e)

    if feed.language:
        kwargs['language'] = feed.language

    if 'tags' in item:
        kwargs['tags'] = filter(None, [x['term'] for x in item.tags])

    if 'author' in item and item.author:
        kwargs['author'] = item.author

    if feed.include_video:
        embed = yield find_video_oembed(item)
        if embed:
            kwargs['video_oembed'] = embed

    kwargs['meta_tags'] = yield get_meta_data_for_url(link)

    kwargs['feed_item'] = item

    raise ndb.Return(kwargs)


@ndb.tasklet
def format_for_adn(entry, feed):
    post_text = entry.title
    links = []
    summary_text = ''
    if feed.include_summary:
        summary_text = strip_html_tags(entry.summary)
        summary_text = ellipse_text(splitter.split(summary_text[0:201])[0], 200)

    if entry.feed_item:
        link = get_link_for_item(feed, entry.feed_item)
    else:
        link = entry.link

    link = iri_to_uri(link)
    link = append_query_string(link, params={'utm_source': 'PourOver', 'utm_medium': 'App.net'})

    # If viewing feed from preview don't shorten urls
    preview = getattr(feed, 'preview', False)
    has_own_bitly_creds = feed.bitly_login and feed.bitly_api_key
    if not preview and (has_own_bitly_creds or feed.format_mode == FORMAT_MODE.TITLE_THEN_LINK):
        if not has_own_bitly_creds:
            feed.bitly_login = 'mixedmedialabs'
            feed.bitly_api_key = 'R_a1311cd1785b7da2aedac9703656b0f1'

        short_url = yield get_short_url(entry, link, feed)
        if short_url:
            link = short_url

    # Starting out it should be as long as it can be
    max_chars = MAX_CHARS
    max_link_chars = 40
    ellipse_link_text = ellipse_text(link, max_link_chars)
    # If the link is to be included in the text we need to make sure we reserve enough space at the end
    if feed.format_mode == FORMAT_MODE.TITLE_THEN_LINK:
        max_chars -= len(' ' + ellipse_link_text)

    # Should be some room for a description
    if len(post_text) < (max_chars - 40) and summary_text:
        post_text = u'%s\n%s' % (post_text, summary_text)

    post_text = ellipse_text(post_text, max_chars)
    if feed.format_mode == FORMAT_MODE.TITLE_THEN_LINK:
        post_text += ' ' + ellipse_link_text

    if feed.format_mode == FORMAT_MODE.TITLE_THEN_LINK:
        links.insert(0, (link, ellipse_link_text))
    else:
        links.insert(0, (link, entry.title))

    link_entities = []
    index = 0
    for href, link_text in links:
        # logger.info('Link info: %s %s %s', post_text, link_text, index)
        text_index = post_text.find(link_text, index)
        if text_index > -1:
            link_entities.append({
                'url': href,
                'text': link_text,
                'pos': text_index,
                'len': len(link_text),
            })
            index = text_index

    post = {
        'text': post_text,
        'annotations': [
            {
                "type": "net.app.core.crosspost",
                "value": {
                    "canonical_url": link
                }
            }
        ]
    }

    if link_entities:
        post['entities'] = {
            'links': link_entities,
        }

    # logger.info('Info %s, %s', include_thumb, self.thumbnail_image_url)
    if feed.include_thumb and entry.thumbnail_image_url:
        post['annotations'].append({
            "type": "net.app.core.oembed",
            "value": {
                "version": "1.0",
                "type": "photo",
                "title": entry.title,
                "width": entry.thumbnail_image_width,
                "height": entry.thumbnail_image_height,
                "url": entry.thumbnail_image_url,
                "thumbnail_width": entry.thumbnail_image_width,
                "thumbnail_height": entry.thumbnail_image_height,
                "thumbnail_url": entry.thumbnail_image_url,
                "embeddable_url": entry.link,
            }
        })

    if feed.include_video and entry.video_oembed:
        oembed = entry.video_oembed
        oembed['embeddable_url'] = entry.link
        post['annotations'].append({
            "type": "net.app.core.oembed",
            "value": oembed
        })

    lang = get_language(entry.language)
    if lang:
        post['annotations'].append({
            "type": "net.app.core.language",
            "value": {
                "language": lang,
            }
        })

    if entry.author:
        post['annotations'].append({
            "type": "net.app.pourover.item.author",
            "value": {
                "author": entry.author,
            }
        })

    if entry.tags:
        post['annotations'].append({
            "type": "net.app.pourover.item.tags",
            "value": {
                "tags": entry.tags,
            }
        })

    raise ndb.Return(post)
