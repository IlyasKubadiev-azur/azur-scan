.PHONY: install dev-windows dev-macos build msi pkg clean run scan-now status

install:
	python -m pip install -e .

dev-windows:
	python -m pip install -e ".[build,windows]"

dev-macos:
	python -m pip install -e ".[build]"

build:
	python build/build.py

msi:
	pwsh -File installer/windows/build.ps1

pkg:
	bash installer/macos/build.sh

run:
	python -m azurscan_agent run

scan-now:
	python -m azurscan_agent scan-now

status:
	python -m azurscan_agent status

clean:
	rm -rf dist build/_pyinstaller_work build/_macos_pkg
