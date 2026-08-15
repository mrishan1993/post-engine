from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config.settings import get_settings
from db.session import get_session, init_db, reset_engine
from first_reel.render import latest_package_dir, render_content_id, render_package_dir, resolve_ffmpeg
from first_reel.runner import run_first_reel
from first_reel.spec import reel_spec

app = typer.Typer(
    help="First Reel Production — Trend→Publish→Analytics→Learning vertical slice",
    no_args_is_help=True,
)
console = Console()


def _init() -> None:
    reset_engine()
    init_db()


@app.command("run")
def run_cmd(
    bootstrap: bool = typer.Option(True, "--bootstrap/--no-bootstrap"),
    character: str = typer.Option("ghost_kid", "--character", "-c"),
    render: bool = typer.Option(True, "--render/--no-render", help="Render silent 9:16 MP4 after package"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Produce Reel #1 through the real pipeline (2016 nostalgia POV)."""
    if not bootstrap:
        console.print("[red]Pass --bootstrap to run the first-reel vertical slice[/red]")
        raise typer.Exit(1)
    _init()
    with get_session() as session:
        result = run_first_reel(session, character_slug=character, publish=True)
        render_info = None
        if render and result.get("package"):
            pkg_path = Path((result["package"]).get("package_path") or "")
            if pkg_path.exists():
                try:
                    render_info = render_package_dir(pkg_path.parent)
                    result["render"] = render_info
                except Exception as exc:  # noqa: BLE001
                    result["render_error"] = str(exc)
        if json_out:
            console.print_json(data={k: v for k, v in result.items() if k != "package"} | {
                "package_path": (result.get("package") or {}).get("package_path"),
                "render_uri": (render_info or {}).get("render_uri"),
            })
            return
        console.print(
            Panel(
                f"ok={result['ok']}\n"
                f"job={result['job_id']} status={result['status']}\n"
                f"content={result['content_id']}\n"
                f"strategy={result['strategy_id']}\n"
                f"campaign={result['campaign_id']}\n"
                f"publication={result['lineage'].get('publication_id')}\n"
                f"package={(result.get('package') or {}).get('package_path')}\n"
                f"render={(render_info or {}).get('render_uri') or result.get('render_error')}\n"
                f"failure={result.get('failure_reason')}",
                title="First Reel #1 — 2016 Phone",
            )
        )
        table = Table(title="Acceptance")
        table.add_column("Check")
        table.add_column("Pass")
        for k, v in (result.get("acceptance") or {}).items():
            table.add_row(k, str(v))
        console.print(table)


@app.command("render")
def render_cmd(
    content_id: str | None = typer.Option(None, "--content-id", "-c", help="Package content id"),
    latest: bool = typer.Option(False, "--latest", help="Render most recent package"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Render silent 9:16 MP4 from a first-reel package (platform-native audio deferred)."""
    if not resolve_ffmpeg():
        console.print("[red]ffmpeg not found — install ffmpeg or place binary at storage/bin/ffmpeg[/red]")
        raise typer.Exit(1)
    if latest or not content_id:
        pkg = latest_package_dir()
        if pkg is None:
            console.print("[red]No first-reel packages under storage/first_reel[/red]")
            raise typer.Exit(1)
        info = render_package_dir(pkg)
        content_id = pkg.name
    else:
        info = render_content_id(content_id)
    if json_out:
        console.print_json(data=info)
        return
    console.print(
        Panel(
            f"content={content_id}\n"
            f"mp4={info['render_uri']}\n"
            f"size={info['width']}x{info['height']} @ {info['fps']}fps\n"
            f"duration={info['duration_sec']}s\n"
            f"audio=deferred (platform_native)",
            title="First Reel render",
        )
    )


@app.command("spec")
def spec_cmd(json_out: bool = typer.Option(True, "--json/--pretty")) -> None:
    """Print the locked creative spec for Reel #1."""
    spec = reel_spec()
    if json_out:
        console.print_json(data=spec)
    else:
        console.print(Panel(str(spec), title=spec["name"]))


if __name__ == "__main__":
    app()
