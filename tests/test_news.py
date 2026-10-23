"""News ingestion never invents X posts or treats headlines as confirmed availability."""
import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from collect_news import parse_rss

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

if __name__=="__main__":unittest.main()
