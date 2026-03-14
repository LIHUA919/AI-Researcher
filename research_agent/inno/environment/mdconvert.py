
from browsergym.core.action.functions import goto, page
from research_agent.inno.environment.markdown_browser import MarkdownConverter


def _get_page_markdown():
    """
    Get the markdown content of the current page

    Examples:
        _get_page_markdown()
    """
    import base64
    import io

    try:
        global page
        phtml = page.evaluate("document.documentElement.outerHTML;")
        mdconvert = MarkdownConverter()
        if page.url == "about:blank":
            raise Exception(
                "You cannot convert the content of the blank page. "
                "It's meaningless. Make sure you have visited a valid page before converting."
            )
        res = mdconvert.convert_stream(io.StringIO(phtml), file_extension=".html", url=page.url)

        clean_md = (
            f"# {res.title}\n\n{res.text_content}\n\n"
            f"If you have not yet got the answer and want to back to the previous page, "
            f"please use `visit_url(url={repr(page.url)})`"
        )

        html_content = f"""
        <html>
        <head>
            <title>{res.title}</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 40px;
                    line-height: 1.6;
                }}
                pre {{
                    white-space: pre-wrap;
                    word-wrap: break-word;
                }}
            </style>
        </head>
        <body>
            <pre>{clean_md}</pre>
        </body>
        </html>
        """

        goto(
            "data:text/html;base64,"
            + base64.b64encode(html_content.encode("utf-8")).decode("utf-8")
        )

        page.evaluate("""
            const event = new Event('pageshow', {
                bubbles: true,
                cancelable: false
            });
            window.dispatchEvent(event);
        """)

    except Exception as e:
        raise Exception(f"Get page markdown error: {str(e)}")


if __name__ == "__main__":
    from playwright.sync_api import sync_playwright
    import io

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        url = "https://www.researchgate.net/publication/232696279_The_influence_of_social_environment_on_sex_determination_in_harlequin_shrimp_Hymenocera_picta_Decapoda_Gnathophyllidae"
        page.goto(url, wait_until="networkidle")

        html = page.evaluate("document.documentElement.outerHTML;")

        mdconvert = MarkdownConverter()
        res = mdconvert.convert_stream(io.StringIO(html), file_extension=".html", url=url)

        print("Title:", res.title)
        print("\nContent:")
        print(res.text_content)

        browser.close()
