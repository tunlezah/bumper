# Command-Line Usage

Start Bumper from the repository directory with `uv run --no-dev bumper` (or `uv run --no-dev python -m bumper`). The available command-line arguments can be viewed by adding the `-h` flag.

````
usage: bumper [-h] [--listen LISTEN] [--announce ANNOUNCE] [--debug]

options:
  -h, --help           show this help message and exit
  --listen LISTEN      start serving on address
  --announce ANNOUNCE  announce address to bots on checkin
  --debug              enable debug logs
````

| Argument     | Description |
| ------------ | ----------- |
| `--listen`   | IP address to start the listeners on. Defaults to `BUMPER_LISTEN`, or else the address the host name resolves to. Use `0.0.0.0` for all interfaces. |
| `--announce` | IP address given to robots when they ask where the server is. Defaults to `BUMPER_ANNOUNCE_IP`, or else the listen address. Set it when listening on `0.0.0.0`. |
| `--debug`    | Debug logging, the same as `BUMPER_DEBUG=true`. |

Example:

````
uv run --no-dev bumper --listen 0.0.0.0 --announce 192.168.1.10
````

Everything else, such as ports, directories and the lowest accepted TLS version, is configured with [environment variables](Env_Var.md).

With the Docker image, arguments after the image name are passed to Bumper, for example `docker run ... ghcr.io/tunlezah/bumper:latest --debug`.
