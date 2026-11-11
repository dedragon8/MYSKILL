#!/usr/bin/env python3
from material_db import connect, DEFAULT_DB
if __name__=='__main__':
    connect().close()
    print(DEFAULT_DB)
