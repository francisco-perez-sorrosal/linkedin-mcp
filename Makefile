# Makefile for building the .dxt package for Claude Extensions

.PHONY: all build clean

all: build

build:
	pixi install
	pixi run update-mcpb-deps
	pixi run mcp-bundle
	pixi run pack

clean:
	pixi clean
	rm -rf mcpb-package/*.mcpb
