"""News ingestion never invents X posts or treats headlines as confirmed availability."""
import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from collect_news import parse_rss,parse_api_news

SAMPLE=b"""<?xml version="1.0"?>
<rss><channel>
<item><title>Milwaukee Bucks update ahead of game</title>
<link>https://www.espn.com/nba/story/_/id/123456/news</link>
<pubDate>Fri, 23 Oct 2026 20:00:00 GMT</pubDate></item>
<item><title>Fake link source</title>
<link>https://not-espn.example/nba/story</link></item>
</channel></rss>"""

class NewsTests(unittest.TestCase):
 def test_clean_news_with_attribution(self):
  rows=parse_rss(SAMPLE,"2026-10-23T21:00:00+00:00")
  self.assertEqual(len(rows),1)
  self.assertEqual(rows[0]["source"],"ESPN NBA RSS")
  self.assertEqual(rows[0]["teams"],["MIL"])
  self.assertFalse(rows[0]["x_post_verified"])
  self.assertFalse(rows[0]["injury_verified"])
  self.assertEqual(rows[0]["published_at_utc"],"2026-10-23T20:00:00+00:00")

class ApiNewsTests(unittest.TestCase):
 def test_verified_provider_article_metadata(self):
  payload={"articles":[{"headline":"Bucks player injury update","published":"2026-10-23T20:00:00Z",
   "byline":"Real ESPN Reporter","links":{"web":{"href":"https://www.espn.com/nba/story/_/id/12345/example"}},
   "categories":[{"type":"team","team":{"abbreviation":"MIL"}}]},
   {"headline":"Spoofed","links":{"web":{"href":"https://spam.example/fake"}}}]}
  news=parse_api_news(payload,"2026-10-23T21:00:00Z")
  self.assertEqual(len(news),1)
  self.assertEqual(news[0]["teams"],["MIL"])
  self.assertEqual(news[0]["author"],"Real ESPN Reporter")
  self.assertFalse(news[0]["x_post_verified"])
  self.assertFalse(news[0]["injury_verified"])
 def test_error_schema(self):
  with self.assertRaises(ValueError):
   parse_api_news({}, "2026-10-23T20:00:00Z")

if __name__=="__main__":unittest.main()
