import asyncio

import click


@click.group()
def cli():
    """The command line interface for benchmark collection tools."""
    pass


@cli.command()
def crawl():
    """Crawl papers from arXiv and build the paper titles dataset."""
    from benchmark_collection import _run_crawl

    _run_crawl()


@cli.command(name="create-graph")
def create_graph():
    """Create the innovation graph from crawled papers."""
    from benchmark_collection import _run_create_graph

    _run_create_graph()


def _run_crawl():
    import importlib
    import sys
    import os

    # The crawl script uses relative imports from its own directory
    original_dir = os.getcwd()
    script_dir = os.path.join(os.path.dirname(__file__))
    os.chdir(script_dir)
    sys.path.insert(0, script_dir)
    try:
        mod = importlib.import_module("benchmark_collection.0_crawl_paper")
        asyncio.run(mod.main())
    finally:
        os.chdir(original_dir)


def _run_create_graph():
    import importlib
    import sys
    import os

    original_dir = os.getcwd()
    script_dir = os.path.join(os.path.dirname(__file__))
    os.chdir(script_dir)
    sys.path.insert(0, script_dir)
    try:
        mod = importlib.import_module("benchmark_collection.1_create_inno_graph")
        asyncio.run(mod.main())
    finally:
        os.chdir(original_dir)
