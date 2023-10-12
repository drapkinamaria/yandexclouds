import ydb
import urllib.parse
import hashlib
import base64
import json
import os


def decode(event, body):
    # тело запроса может быть закодировано
    is_base64_encoded = event.get('isBase64Encoded')
    if is_base64_encoded:
        body = str(base64.b64decode(body), 'utf-8')
    return body


def response(statusCode, headers, isBase64Encoded, body):
    return {
        'statusCode': statusCode,
        'headers': headers,
        'isBase64Encoded': isBase64Encoded,
        'body': body,
    }


def get_config():
    endpoint = os.getenv("endpoint")
    database = os.getenv("database")
    if endpoint is None or database is None:
        raise AssertionError("Нужно указать обе переменные окружения")
    credentials = ydb.construct_credentials_from_environ()
    return ydb.DriverConfig(endpoint, database, credentials=credentials)


def execute(config, query, params):
    with ydb.Driver(config) as driver:
        try:
            driver.wait(timeout=5)
        except TimeoutError:
            print("Connect failed to YDB")
            print("Last reported errors by discovery:")
            print(driver.discovery_debug_details())
            return None

        session = driver.table_client.session().create()
        prepared_query = session.prepare(query)

        return session.transaction(ydb.SerializableReadWrite()).execute(
            prepared_query,
            params,
            commit_tx=True
        )


def insert_name(id, name):
    config = get_config()
    query = """
        DECLARE $id AS Utf8;
        DECLARE $name AS Utf8;

        UPSERT INTO names (id, name) VALUES ($id, $name);
        """
    params = {'$id': id, '$name': name}
    execute(config, query, params)


def find_name(id):
    print(id)
    config = get_config()
    query = """
        DECLARE $id AS Utf8;

        SELECT name FROM names where id=$id;
        """
    params = {'$id': id}
    result_set = execute(config, query, params)
    if not result_set or not result_set[0].rows:
        return None

    return result_set[0].rows[0].name


# def save_name(event):
#     body = event.get('body')
#
#     if body:
#         body = decode(event, body)
#         original_host = event.get('headers').get('Origin')
#         name_id = hashlib.sha256(body.encode('utf8')).hexdigest()[:6]
#         # в ссылке могут быть закодированные символы, например, %. это помешает работе api-gateway при редиректе,
#         # поэтому следует избавиться от них вызовом urllib.parse.unquote
#         insert_name(name_id, urllib.parse.unquote(body))
#         return response(200, {'Content-Type': 'application/json'}, False,
#                         json.dumps({'name': f'{original_host}/r/{name_id}'}))
#
#     return response(400, {}, False, 'В теле запроса отсутствует параметр name')


def save_name(event):
    body = event.get('body')

    if body:
        body = decode(event, body)
        original_host = event.get('headers').get('Origin')
        name_id = hashlib.sha256(body.encode('utf8')).hexdigest()[:6]
        insert_name(name_id, urllib.parse.unquote(body))
        # Вместо возвращения HTML-страницы, верните JSON-ответ
        return response(200, {'Content-Type': 'application/json'}, False,
                        json.dumps({'name': f'{original_host}/r/{name_id}'}))

    # Вместо возвращения текстового HTML-ответа, верните JSON-ответ об ошибке
    return response(400, {'Content-Type': 'application/json'}, False, json.dumps({'error': 'В теле запроса отсутствует параметр name'}))

# def redirect(event):
#     name_id = event.get('pathParams').get('id')
#     redirect_to = find_name(name_id)
#
#     if redirect_to:
#         return response(302, {'Location': redirect_to}, False, '')
#
#     return response(404, {}, False, 'Данной ссылки не существует')


# эти проверки нужны, поскольку функция у нас одна
# в идеале сделать по функции на каждый путь в api-gw
def get_result(name, event):
    if name == "/save_name":
        return save_name(event)
    # if full_name.startswith("/r/"):
    #     return redirect(event)

    return response(404, {}, False, 'Данного пути не существует')


def handler(event, context):
    name = event.get('name')
    if name:
        # из API-gateway url может прийти со знаком вопроса на конце
        if name[-1] == '?':
            name = name[:-1]
        return get_result(name, event)

    return response(404, {}, False, 'Эту функцию следует вызывать при помощи api-gateway')

