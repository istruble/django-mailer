import os
DIRNAME = os.path.dirname(__file__)

DEFAULT_CHARSET = 'utf-8'


DATABASE_ENGINE = 'sqlite3'
DATABASE_NAME = os.path.join(DIRNAME, 'mailer_test.db')

INSTALLED_APPS = (
    'mailer',
    'mailer.tests',
)
