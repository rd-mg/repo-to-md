import asyncio
from urllib.parse import urlparse, urljoin
from datetime import datetime
import trafilatura
from playwright.sync_api import sync_playwright
from playwright.async_api import async_playwright
from fake_useragent import UserAgent
from .base import BaseProcessor

class WebProcessor(BaseProcessor):
    def crawl_website(self, start_url, output_file, max_pages=100):
        """Synchronous version for compatibility with Tkinter and current CLI."""
        ua = UserAgent()
        domain = urlparse(start_url).netloc
        visited = set()
        to_visit = [start_url]
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=ua.random)
            
            with open(output_file, 'w', encoding='utf-8') as md:
                md.write(f"---\ntitle: \"Web Digest: {domain}\"\ndate: {datetime.now().strftime('%Y-%m-%d')}\n---\n\n")
                
                pages_count = 0
                while to_visit and pages_count < max_pages:
                    url = to_visit.pop(0)
                    if url in visited: continue
                    visited.add(url)
                    
                    self.log(f"Scraping: {url}")
                    try:
                        page.goto(url, wait_until='domcontentloaded', timeout=60000)
                        content = trafilatura.extract(page.content(), output_format='markdown')
                        if content:
                            md.write(f"### Source: {url}\n\n{content}\n\n---\n\n")
                            pages_count += 1
                            
                            for link in [a.get_attribute('href') for a in page.query_selector_all('a[href]')]:
                                full_url = urljoin(url, link)
                                if urlparse(full_url).netloc == domain and full_url not in visited:
                                    to_visit.append(full_url)
                    except Exception as e:
                        self.log(f"Error: {e}")
            browser.close()
        return pages_count

    async def async_crawl_website(self, start_url, output_file, max_pages=100, concurrency=5):
        """Asynchronous version for high performance."""
        ua = UserAgent()
        domain = urlparse(start_url).netloc
        visited = set()
        to_visit = asyncio.Queue()
        await to_visit.put(start_url)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            # Use a semaphore to limit concurrency
            sem = asyncio.Semaphore(concurrency)
            pages_count = 0
            
            # File writing (synchronous but we can use a lock or aiofiles)
            # For simplicity in this example, we'll collect content and write at the end or use a lock
            file_lock = asyncio.Lock()
            
            with open(output_file, 'w', encoding='utf-8') as md:
                md.write(f"---\ntitle: \"Web Digest: {domain} (Async)\"\ndate: {datetime.now().strftime('%Y-%m-%d')}\n---\n\n")

            async def scrape_page(url):
                nonlocal pages_count
                if url in visited or pages_count >= max_pages:
                    return
                visited.add(url)
                
                async with sem:
                    self.log(f"Scraping: {url}")
                    context = await browser.new_context(user_agent=ua.random)
                    page = await context.new_page()
                    try:
                        await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                        content = trafilatura.extract(await page.content(), output_format='markdown')
                        
                        if content:
                            async with file_lock:
                                with open(output_file, 'a', encoding='utf-8') as md:
                                    md.write(f"### Source: {url}\n\n{content}\n\n---\n\n")
                                pages_count += 1
                            
                            links = await page.query_selector_all('a[href]')
                            for link in links:
                                href = await link.get_attribute('href')
                                full_url = urljoin(url, href)
                                if urlparse(full_url).netloc == domain and full_url not in visited:
                                    await to_visit.put(full_url)
                    except Exception as e:
                        self.log(f"Error on {url}: {e}")
                    finally:
                        await context.close()

            # Main crawl loop
            tasks = []
            while pages_count < max_pages:
                try:
                    # If we have tasks and the queue is empty, wait for a bit
                    if to_visit.empty():
                        if not tasks: break
                        await asyncio.sleep(0.1)
                        continue
                    
                    url = await to_visit.get()
                    task = asyncio.create_task(scrape_page(url))
                    tasks.append(task)
                    
                    # Clean up completed tasks
                    tasks = [t for t in tasks if not t.done()]
                    
                except Exception as e:
                    self.log(f"Loop error: {e}")
                    break
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                
            await browser.close()
        return pages_count
