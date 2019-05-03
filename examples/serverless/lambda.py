import json


def handler(evt, ctx):
    return {
        "statusCode": 200,
        "body": json.dumps('hello. world.')
    }
