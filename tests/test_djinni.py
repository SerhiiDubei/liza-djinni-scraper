import httpx

from liza.scraper.djinni import fetch_all, fetch_vacancies

PAGE1 = """
<html><head>
<script type="application/ld+json">
{"@type":"JobPosting","title":"Python Dev","url":"https://djinni.co/jobs/1/",
 "hiringOrganization":{"name":"ACME"}}
</script>
</head><body>
<a href="?page=1">1</a><a href="?page=2">2</a>
</body></html>
"""
EMPTY = "<html><body>nothing</body></html>"


def _transport():
    def handler(req):
        page = req.url.params.get("page", "1")
        return httpx.Response(200, text=PAGE1 if page == "1" else EMPTY)
    return httpx.MockTransport(handler)


async def test_fetch_vacancies_paginates_and_tags_category():
    vacancies = await fetch_vacancies(keyword="Python", transport=_transport())
    assert len(vacancies) == 1
    assert vacancies[0].title == "Python Dev"
    assert vacancies[0].category == "Python"   # tagged from keyword


async def test_fetch_all_dedups_across_keywords_by_url():
    out = await fetch_all(keywords=["Python", "Django"], transport=_transport())
    assert len(out) == 1   # same url from both keyword runs collapses to one


def _multipage_transport(n):
    def handler(req):
        page = int(req.url.params.get("page", "1"))
        if page > n:
            return httpx.Response(200, text="<html><body></body></html>")
        links = "".join('<a href="?page=%d">%d</a>' % (k, k) for k in range(1, n + 1))
        jp = ('{"@type":"JobPosting","title":"Job %d",'
              '"url":"https://djinni.co/jobs/%d/"}' % (page, page))
        html = ('<html><head><script type="application/ld+json">%s</script></head>'
                '<body>%s</body></html>' % (jp, links))
        return httpx.Response(200, text=html)
    return httpx.MockTransport(handler)


async def test_full_scrape_pulls_all_pages():
    out = await fetch_vacancies(max_pages=None, transport=_multipage_transport(5))
    assert len(out) == 5


async def test_incremental_respects_page_cap():
    out = await fetch_vacancies(max_pages=2, transport=_multipage_transport(5))
    assert len(out) == 2
