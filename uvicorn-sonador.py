#!/usr/bin/env python
'''	Sonador run script for Uvicorn. Sets the default host and port to match
	Sonador defaults:

	* Host: 0.0.0.0
	* Port: 8070
'''
import os, sys
import uvicorn
import importlib


# Set Sonador default settings
os.environ.setdefault('UVICORN_HOST', '0.0.0.0')
os.environ.setdefault('UVICORN_PORT', '8070')


# Monkeypatch UVicorn function to import app before launching server
orig_run = uvicorn.run


def run(*args, **kwarg):
	importlib.import_module(args[0])

	orig_run(*args, **kwarg)


uvicorn.run = run


if __name__ == '__main__':
	'''	Start Uvicorn programitcally after initializing Django application.
	'''
	if len(sys.argv) == 1 or not 'sonador.asgi:application' in sys.argv:
		sys.argv.append('sonador.asgi:application')
	
	uvicorn.main()