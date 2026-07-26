"""CLI entry point: Typer app launching uvicorn."""

from __future__ import annotations

from pathlib import Path

import typer

__all__ = ("app", "main")

app = typer.Typer(
    name="birec",
    help="Bilibili live-stream recorder",
    add_completion=False,
)


@app.command()
def run(
    version: bool = typer.Option(
        False, "--version", "-V", help="Show version and exit"
    ),
    config: Path = typer.Option(
        Path("config.toml"), "--config", "-c", help="Config file path"
    ),
    output: Path = typer.Option(
        Path("./recordings"), "--output", "-o", help="Output directory"
    ),
    log_dir: Path = typer.Option(Path("./logs"), "--log-dir", help="Log directory"),
    progress: bool = typer.Option(
        True, "--progress/--no-progress", help="Show progress"
    ),
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(2233, "--port", help="Bind port"),
    open_browser: bool = typer.Option(False, "--open", help="Open browser on start"),
    ipv4: bool = typer.Option(False, "--ipv4", help="Force IPv4"),
    root_path: str = typer.Option(
        "", "--root-path", help="Root path for reverse proxy"
    ),
    key_file: Path | None = typer.Option(None, "--key-file", help="SSL key file"),
    cert_file: Path | None = typer.Option(None, "--cert-file", help="SSL cert file"),
) -> None:
    """Start the bili-rec server."""
    if version:
        from birec import __version__

        typer.echo(f"birec {__version__}")
        raise typer.Exit()

    import uvicorn

    from birec.application import create_application

    application = create_application(
        config_path=config,
        output_dir=output,
        log_dir=log_dir,
    )

    ssl_kwargs: dict[str, str] = {}
    if key_file and cert_file:
        ssl_kwargs["ssl_keyfile"] = str(key_file)
        ssl_kwargs["ssl_certfile"] = str(cert_file)

    uvicorn.run(
        application,
        host=host,
        port=port,
        root_path=root_path,
        **ssl_kwargs,  # type: ignore[arg-type]
    )


def main() -> None:
    """Entry point for the CLI."""
    app()
