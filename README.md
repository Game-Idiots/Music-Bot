# Music Bot
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

# Feel free to Contributors :D

## Use our hosted Version

# [Invite Bot]() Coming soon

## Acknowledgments

### Special Thanks

- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** - For providing the core functionality


### Resources

This folder contains the Music bot service, packaged for Docker. Use the instructions below to run it locally or in a container(recommended).


## Prerequisites

- Python 3.11+
- Docker (optional, for container run)
- A `.env` file (or environment variables) with the bot configuration

## Configure

1. Create a `.env` file in this folder.
2. Add the required configuration values for your bot. Example:

```
DISCORD_TOKEN=your-token-here

```

If your version uses additional settings, add them to the same file.

## Run locally

```
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python bot.py
```

## Run with Docker

```
docker build -t music-bot .
docker run --env-file .env music-bot
```

## Notes

- The `playlists.db` file is created/used at runtime for local storage.
- If you need persistent data in Docker, mount a volume for the folder.

### Contributors

Thanks to all the amazing contributors who have helped make this project better!

[![Contributors](https://github.com/Game-Idiots/Music-Bot/graphs/contributors)](https://github.com/username/repo/graphs/contributors)

## Our version

If you are using our hosted or deployed version, request the `DISCORD_TOKEN` and any other environment values from the team, then follow the same run steps above.

##  Team
<table>
  <tr>
    <td align="center">
      <img src="https://avatars.githubusercontent.com/u/131915994?s=400&u=226eaf9b75e6d710ae7c65ade6f70efd77b1d9f5&v=4" width="100px" alt=""/><br />
      <b>atfam</b><br />
      <i>Lead Developer</i><br />
      <a href="https://github.com/atfam">GitHub</a>
    </td>


