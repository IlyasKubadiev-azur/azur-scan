"""Entry point for `python -m azurscan_agent` and the PyInstaller binary.

Use absolute import — relative imports break in frozen onefile mode where
__main__ has no parent package. The `azurscan_agent` package is on sys.path
in both contexts (PyInstaller bundle root / installed package), so the
absolute form works everywhere.
"""
from azurscan_agent.cli import cli


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
