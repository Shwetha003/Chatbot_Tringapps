import sys
import asyncio
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

from app.services.chunking import create_chunks
from app.crud.chat import save_chunk
from app.services.embedding_services import create_embedding

def parse_page_by_headings(html_content: str, is_wikipedia: bool = False) -> list:
    soup = BeautifulSoup(html_content, "html.parser")
    for layout in soup(["script", "style", "nav", "footer", "header", "form", "aside"]):
        layout.decompose()
    main_content = soup.find(id="mw-content-text") if is_wikipedia else soup.body
    if not main_content:
        main_content = soup
    noise_selectors = [
        ".mw-portlet", "#siteSub", "#contentSub", ".mw-jump-link",
        ".navbox", ".catlinks", ".printfooter", ".infobox",
        ".reference", ".reflist", ".language-list", "#p-lang",
        ".mw-editsection",
    ]
    for selector in noise_selectors:
        for match in main_content.select(selector):
            match.decompose()
    raw_elements = []
    elements = main_content.find_all(["h1", "h2", "h3", "p", "span"])
    for element in elements:
        if element.name == "span":
            if not ("text" in element.get("class", []) or "author" in element.get("class", []) or element.get("itemprop") == "text"):
                continue
        text = element.get_text().strip()
        if text in ["Login","Sign Up","Next →","← Previous","Contents","See also","References","Quotes to Scrape","Top Ten tags"]:
            continue
        if text and text not in raw_elements:
            raw_elements.append(text)
    return raw_elements

def extract_internal_links(html_content: str, current_url: str, target_domain: str) -> list:
    soup = BeautifulSoup(html_content, "html.parser")
    sublinks = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        full_url = urljoin(current_url, href)
        parsed_url = urlparse(full_url)
        if parsed_url.netloc == target_domain:
            clean_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
            if clean_url not in sublinks:
                sublinks.append(clean_url)
    return sublinks

def run_heading_crawler(start_url: str, db, document_id: int) -> str:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    target_domain = urlparse(start_url).netloc
    is_wiki = "wikipedia.org" in start_url

    async def main_scrape():
        visited_urls = set()
        queued_urls = {start_url}
        seen_text_content = set()
        display_output = []
        url_queue = asyncio.Queue()
        await url_queue.put(start_url)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            visited_lock = asyncio.Lock()
            content_lock = asyncio.Lock()

            async def worker(worker_id: int):
                page = await context.new_page()
                try:
                    while True:
                        current_url = await url_queue.get()
                        try:
                            async with visited_lock:
                                if current_url in visited_urls:
                                    continue
                                visited_urls.add(current_url)

                            print(f"[Worker {worker_id}] Scraping -> {current_url}")

                            response = await page.goto(current_url, wait_until="domcontentloaded", timeout=15000)

                            if not response or response.status >= 400:
                                continue

                            html_content = await page.content()

                            page_lines = parse_page_by_headings(html_content, is_wikipedia=is_wiki)

                            async with content_lock:
                                for line in page_lines:
                                    norm_line = " ".join(line.split()).lower()
                                    if "viewing tag:" in norm_line:
                                        continue
                                    if norm_line not in seen_text_content:
                                        seen_text_content.add(norm_line)
                                        display_output.append(line)

                            new_sublinks = extract_internal_links(html_content, current_url, target_domain)

                            async with visited_lock:
                                for sublink in new_sublinks:
                                    if sublink not in visited_urls and sublink not in queued_urls:
                                        queued_urls.add(sublink)
                                        await url_queue.put(sublink)

                        except Exception:
                            pass
                        finally:
                            url_queue.task_done()
                finally:
                    await page.close()

            workers = [asyncio.create_task(worker(i)) for i in range(10)]

            await url_queue.join()

            for task in workers:
                task.cancel()

            await asyncio.gather(*workers, return_exceptions=True)

            await context.close()
            await browser.close()

            print(f"Pages scraped: {len(visited_urls)}")

        full_text = "\n\n".join(display_output)
        chunks = create_chunks(full_text)

        for chunk in chunks:
            embedding = create_embedding(chunk)
            print("SAVING CHUNK EMBEDDING SIZE:", len(embedding))
            save_chunk(
                db=db,
                document_id=document_id,
                chunk_content=chunk,
                embedding=embedding
            )

        return full_text

    new_loop = asyncio.new_event_loop()

    try:
        return new_loop.run_until_complete(main_scrape())
    finally:
        new_loop.close()

async def scrape_to_pure_text(url: str, db, document_id: int) -> str:
    loop = asyncio.get_running_loop()

    with ThreadPoolExecutor(max_workers=1) as executor:
        return await loop.run_in_executor(
            executor,
            run_heading_crawler,
            url,
            db,
            document_id
        )