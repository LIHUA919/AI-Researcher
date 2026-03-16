"""Tests for CLI entry points using click.testing.CliRunner."""

from click.testing import CliRunner


class TestResearchAgentCli:
    def test_help(self):
        from research_agent.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "command line interface" in result.output.lower()

    def test_default_dummy_agent_is_importable(self):
        import research_agent.inno.agents as agents

        assert hasattr(agents, "get_dummy_agent")


class TestPaperAgentCli:
    def test_help(self):
        from paper_agent.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "paper writing agent" in result.output.lower()

    def test_write_help(self):
        from paper_agent.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["write", "--help"])
        assert result.exit_code == 0
        assert "--research_field" in result.output


class TestBenchmarkCli:
    def test_help(self):
        from benchmark_collection.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "benchmark collection" in result.output.lower()

    def test_crawl_help(self):
        from benchmark_collection.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["crawl", "--help"])
        assert result.exit_code == 0

    def test_create_graph_help(self):
        from benchmark_collection.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["create-graph", "--help"])
        assert result.exit_code == 0
