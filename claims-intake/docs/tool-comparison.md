# Tool comparison

I used Cursor only. There was no second agent.

The task I did in Cursor was the README: how to run the service, how to run
the tests, and why we build with `--platform linux/amd64`.

## What Cursor made easy

It was already in this repo. It read `routes.py` and used
`claims.api.routes:app` instead of guessing a module name. It saw
`Linux aarch64` and `docker: command not found`, so the README could say this
environment is ARM, Docker is not installed here, and the image is built on a
machine that has Docker.

It started uvicorn. A `POST /notifications` returned `201`, which is what a
new joiner should see.

## What Cursor made awkward

It tried `docker buildx` in this container. That fails. I kept that command
for a host that has Docker. Opening a pull request, reading Checks, and
checking whether merge is blocked are GitHub work. Cursor cannot do those
clicks. Short commands I already know (`uv run pytest`) are faster if I type
them.

## When I use Cursor

I use Cursor for work that has to match this tree: README, HTTP mapping,
tests, Dockerfile. It can read the files and see a missing `docker` binary.

I do GitHub, `/docs`, and the terminal myself when I already know the next
click.
