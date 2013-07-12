from bs4 import BeautifulSoup
import feedparser

DEFAULT_ENTRY_TEMPLATE = "{{title}} - {{summary}} {{link_text}}"
MAX_CHARS = 256
LIMIT_URL = 40

TOKENS = [
    "title",
    "summary",
    "link",
]


def shorten_text(overrun, text):
    if len(text) > overrun:
        text = text[0: len(text) - overrun]
    else:
        text = ''

    return text


class FeedParser(object):

    def __init__(self, data):
        self.data = feedparser.parse(data)
        self.raw_data = data

    def context_from_entry(self, entry):
        context = {}
        context['title'] = entry.title
        context['link'] = entry.link
        summary = BeautifulSoup(entry.get('summary', ''))
        context['summary'] = summary.get_text()
        # context['summary_html'] = summary
        context['guid'] = entry.guid

        return context

    def format_entry(self, entry):
        entry_context = self.context_from_entry(entry)
        post_text = u'%(title)s - %(summary)s' % entry_context
        if len(post_text) > MAX_CHARS:
            post_text = post_text[0:MAX_CHARS - 1] + u'\u2026'

        post = {
            'text': post_text,
        }

        # What about images?
        # What about video?

        if entry_context['link']:
            post['entities'] = {
                'links': [{
                    'url': entry_context['link'],
                    'pos': 1,
                    'len': len(entry_context['title'])
                }]
            }

        return (entry_context, post)

    # def format_entry(self, entry):
    #     # Starting off its as long as it possibly can be
    #     max_chars = MAX_CHARS

    #     # In a template a user may enter text that will appear in every post
    #     # those are static chars and we must work around them, so
    #     # we need to know how many of them there are.
    #     static_chars = self.entry_template
    #     for token in TOKENS:
    #         static_chars = static_chars.replace('{{%s}}' % (token,), '')

    #     # Now from here we try and fit in everything else around it.
    #     max_chars = max_chars - len(static_chars)

    #     title = title_display = entry.title
    #     link = link_display = entry.link
    #     if len(link) > LIMIT_URL:
    #         link_display = link[0:LIMIT_URL]

    #     summary = BeautifulSoup(entry.summary)
    #     summary_text = summary_display = summary.get_text()

    #     msg_len = len(summary_display) + len(title_display) + len(link_display) + len(static_chars)
    #     if msg_len > max_chars:
    #         # First try and shorten up the summary
    #         summary_display = shorten_text(msg_len - max_chars, summary_display)

    #     msg_len = len(summary_display) + len(title_display) + len(link_display) + len(static_chars)
    #     if msg_len > max_chars:
    #         # Then try and shorten the title
    #         title_display = shorten_text(msg_len - max_chars, title_display)

    #     post_text = self.entry_template
    #     post_text = post_text.replace('{{title}}', title_display)
    #     post_text = post_text.replace('{{summary}}', summary_display)

    #     start_link = post_text.find('{{link_text}}')
    #     if start_link >= 0:
    #         post_text = post_text.replace("{{link_text}}", link_display)

    #     return post_text

    def process_entries(self):
        for entry in self.data.entries:
            yield self.format_entry(entry)
