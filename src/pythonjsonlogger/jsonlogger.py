import json
import logging
import traceback
from datetime import datetime
from collections import OrderedDict


class JsonFormatter(logging.Formatter):
    """
    A custom formatter to format logging records as json strings.
    extra fields can be added to the json structure by adding the key name in RESERVED_ATTRS
    """

    RESERVED_ATTRS = {
        'args', 'asctime', 'created', 'exc_info', 'exc_text', 'filename',
        'funcName', 'levelname', 'levelno', 'lineno', 'module',
        'msecs', 'message', 'msg', 'name', 'pathname', 'process',
        'processName', 'relativeCreated', 'stack_info', 'thread', 'threadName'
    }

    def __init__(self, *args, **kwargs):
        """
        :param json_default: a function for encoding non-standard objects
            as outlined in https://docs.python.org/3/library/json.html
        :param json_encoder: optional custom encoder
        :param json_serializer: a :meth:`json.dumps`-compatible callable
            that will be used to serialize the log record.
        :param json_indent: an optional :meth:`json.dumps`-compatible numeric value
            that will be used to customize the indent of the output json.
        :param prefix: an optional string prefix added at the beginning of
            the formatted string
        :param rename_fields: an optional dict, used to rename field names in the output.
            Rename 'foo' to 'bar': {'foo': 'bar'}
        :param static_fields: an optional dict, used to add fields with static values to all logs
        :param timestamp: an optional string/boolean field to add a timestamp to the log records
        """
        self.json_default = self._str_to_fn(kwargs.pop("json_default", None))
        self.json_encoder = self._str_to_fn(kwargs.pop("json_encoder", None))
        self.json_serializer = self._str_to_fn(kwargs.pop("json_serializer", json.dumps))
        self.json_indent = kwargs.pop("json_indent", None)
        self.prefix = kwargs.pop("prefix", "")
        self.rename_fields = kwargs.pop("rename_fields", {})
        self.static_fields = kwargs.pop("static_fields", {})
        self.timestamp = kwargs.pop("timestamp", None)
        # super(JsonFormatter, self).__init__(*args, **kwargs)
        logging.Formatter.__init__(self, *args, **kwargs)
        if not self.json_encoder and not self.json_default:
            def _default_json_handler(obj):
                """Prints dates in ISO format"""
                if isinstance(obj, (datetime, date)):
                    return obj.isoformat()
                elif isinstance(obj, uuid.UUID):
                    return str(obj)
                elif isinstance(obj, Exception):
                    return str(obj)
                try:
                    return str(obj)
                except Exception:
                    return None
            self.json_default = _default_json_handler
        self._required_fields = self.parse()
        self._skip_fields = dict(zip(self._required_fields,
                                     self._required_fields))
        self._skip_fields.update(self.rename_fields)

    def _str_to_fn(self, fn_as_str):
        """
        If the argument is not a string, return whatever was passed in.
        Parses a string such as package.module.function return the function.
        """
        if not isinstance(fn_as_str, str):
            return fn_as_str

        path, _, function = fn_as_str.rpartition('.')
        module = importlib.import_module(path)
        return getattr(module, function)

    def parse(self):
        """
        Parses format string looking for substitutions
        This method is responsible for returning a list of fields (as strings)
        to include in all log messages.
        """
        standard_formatters = re.compile(r'((.+?))', re.IGNORECASE)
        return standard_formatters.findall(self._fmt)

    def add_fields(self, log_record, record, message_dict):
        """
        Override this method to implement custom logic for adding fields.
        """
        for field in self._required_fields:
            log_record[field] = record.__dict__.get(field)
        log_record.update(self.static_fields)
        log_record.update(message_dict)
        if self.timestamp:
            key = self.timestamp if isinstance(self.timestamp, str) else 'timestamp'
            log_record[key] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def process_log_record(self, log_record):
        """
        Override this method to implement custom logic
        on the possibly ordered dictionary.
        """
        return log_record

    def jsonify_log_record(self, log_record):
        """Returns a json string of the log record."""
        return self.json_serializer(log_record,
                                    default=self.json_default,
                                    cls=self.json_encoder,
                                    indent=self.json_indent)

    def format(self, record):
        """Formats a log record and serializes to json"""
        message_dict = {}
        if isinstance(record.msg, dict):
            message_dict = record.msg
            record.message = None
        else:
            record.message = record.getMessage()
        # only format time if needed
        if "asctime" in self._required_fields:
            record.asctime = self.formatTime(record, self.datefmt)

        # Display formatted exception, but allow overriding it in the
        # user-supplied dict.
        if record.exc_info and not message_dict.get('exc_info'):
            message_dict['exc_info'] = self.formatException(record.exc_info)
        if not message_dict.get('exc_info') and record.exc_text:
            message_dict['exc_info'] = record.exc_text
        # Display formatted record of stack frames
        # default format is a string returned from :func:`traceback.print_stack`
        if record.stack_info and not message_dict.get('stack_info'):
            message_dict['stack_info'] = self.formatStack(record.stack_info)

        try:
            log_record = OrderedDict()
        except NameError:
            log_record = {}

        self.add_fields(log_record, record, message_dict)
        log_record = self.process_log_record(log_record)

        # Add event type for AU-2 compliance
        log_record['event_type'] = record.levelname

        return "%s%s" % (self.prefix, self.jsonify_log_record(log_record))