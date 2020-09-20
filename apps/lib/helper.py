from datetime import datetime

from lib.context import PartsOfDay


def list_value(value, default=[]):
    if value is None:
        return default

    if isinstance(value, list):
        return _flatten_list_arg(value)

    return [value]


def _flatten_list_arg(arg_value):
    values = []
    for value in arg_value:
        if isinstance(value, list):
            values.extend(_flatten_list_arg(value))
        else:
            values.append(value)

    return values


def to_int(str, default_value=None):
    if str is None:
        return default_value

    return int(round(to_float(str, default_value)))


def to_float(str, default_value=None):
    if str is None:
        return default_value

    try:
        return float(str)
    except ValueError:
        if default_value is None:
            raise

    return default_value


def create_ios_push_data(category, entity_id=None, action_data=None,
                         attachment=None):
    data = {
        'push': {
            'category': category
        },
    }

    if entity_id is not None:
        data['entity_id'] = entity_id

    if action_data is not None:
        data['action_data'] = action_data

    if attachment is not None:
        data['attachment'] = attachment

    return data


def concat_list(items, concat_str=', '):
    if not items:
        return None

    length = len(items)
    if length == 1:
        return items[0]
    else:
        return concat_str.join(items[:-1]) + concat_str + " and " + str(
            items[-1])


def figure_parts_of_day():
    now = datetime.now()
    if today_at(4, 0) <= now < today_at(12, 0):
        return PartsOfDay.MORNING
    elif today_at(12, 0) <= now < today_at(17, 0):
        return PartsOfDay.AFTERNOON
    elif today_at(17, 0) <= now < today_at(20, 0):
        return PartsOfDay.EVENING
    else:
        return PartsOfDay.NIGHT


def today_at(hour, min):
    return datetime.now().replace(hour=hour, minute=min, second=0,
                                  microsecond=0)


def to_datetime(str):
    if str is None:
        return None

    if len(str) == 32:
        # 2019-12-02T19:02:07.776968+00:00
        str = str[::-1].replace(':', '', 1)[::-1]
        return datetime.strptime(str, '%Y-%m-%dT%H:%M:%S.%f%z')

    return None
