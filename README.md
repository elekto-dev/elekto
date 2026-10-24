![banner.js](/static/banner.png)

**elekto** is a flask based web application for conducting online elections. It Implements the [condorcet method](https://en.wikipedia.org/wiki/Condorcet_method).

The project was created as the part of [Cloud Native Computing Foundation's Internship](https://github.com/kubernetes/community/issues/5096) via [The Linux Foundation mentorship](https://docs.linuxfoundation.org/lfx/mentorship) program, to run community and steering elections for CNCF and LF projects.

## Getting Started

The application requires a [meta]() repository to store election meta files. The meta repository is the single source of truth for the application and is managed by gitops, all the tasks like creating an election, adding/removing voters to the list are managed by raising specific pull requests in the meta repository. See our detailed instruction [docs](/docs/README.md)

![architecture.png](/static/arch.png)

## To start using elekto

#### Create a development environment

The application is written in `python` using `flask` and `sqlalchemy`. This repository ships a `requirements.txt` and a `environment.yml` for conda users.

```bash
# Installation with pip
pip install -r requirements.txt

# Installation with Conda
conda env create -f environment.yml && conda activate elekto
```

#### Setup env variables

The repository has a `.env.example` file which can be used as a template for `.env` file, update the environment file after copying from `.env.example`.

```bash
# create a new .env file from .env.example
cp .env.example .env
```

Set the basic information about the application in the upper section

```bash
APP_NAME=k8s.elections     # set the name of the application
APP_ENV=development        # development | production
APP_KEY=                   # random secret key (!! important !!)
APP_DEBUG=True             # True | False (production)
APP_URL=http://localhost   # Url where the application is hosted
APP_PORT=5000              # Default Running port for development
APP_HOST=localhost         # Default Host for developmemt
```

Update the database credentials,

```bash
DB_CONNECTION=mysql        # Mysql is only supported
DB_HOST=localhost
DB_PORT=3306
DB_DATABASE=name
DB_USERNAME=user
DB_PASSWORD=password
```

Update the meta repository info

```bash
META_REPO=https://github.com/elekto-dev/elekto.meta.test.git
META_DEPLOYMENT=local
META_PATH=meta
META_BRANCH=main
META_SECRET=  # same as webhook of the same meta repository
```

Update the Oauth info, create an github oauth app if already not created.

```bash
GITHUB_REDIRECT=/oauth/github/callback
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
```

#### Migrate and Sync DB with Meta

The `console` script in the repository is used to perform all the table creations and syncing of the meta.

```bash
# to migrate the database from command line
python console --migrate
```

To sync the database with the meta files

```bash
# to the sync the database with the meta
python console --sync
```

#### Run the application Server locally

The flask server will start on `5000` by default but can be changed using `--port` option.

```bash
# to run the server on default configs
python console --run

# to change host and port
python console --port 8080 --host 0.0.0.0 --run
```

#### Run with Docker Compose

To run the app and a Postgres database together, create a `.env` file and set `APP_KEY` and `META_SECRET`.
Signing in needs a GitHub OAuth app, so also set `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET`; public pages work
without them. The database settings in `.env` are overridden to use the Compose database.

```bash
cp .env.example .env
docker compose up --build
```

Then open http://localhost:5000.

### Running tests
Commands are available to run the test suite. This suite currently only consists of unit tests. A prerequisite for 
running the test suite is that you have a virtualenv setup. This can be done by running `make venv`. To run the tests,
do `make test`.

Coverage is available. A report can be generated with `make cov`.

### Contact Us

See the website at [Elekto.dev](https://elekto.dev).

Elekto is a project of the CNCF, and you can reach us on [CNCF Slack](https://slack.cncf.io/),
channel #elekto.
