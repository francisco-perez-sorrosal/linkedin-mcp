# Makefile for building the .dxt package for Claude Extensions

.PHONY: all build clean

all: build

build:
	pixi install
	pixi run bundle
	pixi run pack

clean:
	rm -rf dxt-package/*.dxt
