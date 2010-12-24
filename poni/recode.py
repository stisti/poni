"""
Data type conversions

Copyright (c) 2010 Mika Eloranta
See LICENSE for details.

"""

# TODO: pg_size_pretty() style output formatting, e.g. 1024 -> 1k 

import os
import re
import codecs
import json
import socket

class Error(Exception):
    """recode error"""

class EncodeError(Error):
    """encode error"""
    
class InvalidCodecDefinition(Error):
    """invalid codec definition"""


ENCODE = "+"
DECODE = "-"

re_coder = re.compile("([-+]?)([a-z0-9_-]+)", re.I)

def int_convert(x):
    return int(x, 0) # supports binary, octal, decimal and hex formats

def from_env(value):
    try:
        return os.environ[value]
    except KeyError:
        raise ValueError("environment variable %r is not set" % value)

def resolve_ip(name, family):
    try:
        addresses = socket.getaddrinfo(name, None, family)
    except (socket.error, socket.gaierror), error:
        raise EncodeError("resolving %r failed: %s: %s" % (
            name, error.__class__.__name__, error))

    if not addresses:
        raise EncodeError("name %r does not resolve to any addresses" % name)

    return addresses[0][-1][0]

multiples = {
    # SI
    "k": 10 ** 3,
    "M": 10 ** 6,
    "G": 10 ** 9,
    "T": 10 ** 12,
    "P": 10 ** 15,
    "E": 10 ** 18,
    "Z": 10 ** 21,
    "Y": 10 ** 24,

    # IEEE 1541
    'Ki': 2 ** 10,
    'Mi': 2 ** 20,
    'Gi': 2 ** 30,
    'Ti': 2 ** 40,
    'Pi': 2 ** 50,
    'Ei': 2 ** 60,
    }

RE_MULT = re.compile("(.*)(%s)$" % ("|".join(multiples)))

def convert_num(cls, value):
    match = RE_MULT.match(value)
    if match:
        num_val = cls(match.group(1))
        return num_val * multiples[match.group(2)]
    else:
        return cls(value)
    
BOOL_MAP = {"true": True, "1": True, "on": True,
            "false": False, "0": False, "off": False}

def to_bool(value):
    try:
        return BOOL_MAP[value]
    except KeyError:
        raise ValueError("invalid boolean value: %r, expected one of: %s" % (
            value, ", ".join(repr(x) for x in BOOL_MAP)))

type_conversions = {
    "str": (str, None), 
    "int": (lambda x: convert_num(int_convert, x), None),
    "float": (lambda x: convert_num(float, x), None),
    "bool": (to_bool, None),
    "json": (json.dumps, json.loads),
    "null": (lambda x: None, None),
    "eval": (eval, None),
    "env": (from_env, None),
    "ipv4": (lambda name: resolve_ip(name, socket.AF_INET), None),
    "ipv6": (lambda name: resolve_ip(name, socket.AF_INET6), None),
    }


class Codec:
    def __init__(self, chain_str, default=None):
        self.default = default
        self.chain = []
        self.parse_chain(chain_str)

    def parse_chain(self, chain_str):
        parts = chain_str.split(":")
        for part in parts:
            match = re_coder.match(part)
            if not match:
                raise InvalidCodecDefinition(
                    "invalid codec definition: %r, at %r" % (chain_str, part))

            direction, codec_name = match.groups()
            self.add_to_chain(codec_name, direction)

    def get_coder(self, codec_name, direction):
        converters = type_conversions.get(codec_name)
        if converters:
            if direction == DECODE:
                converter = converters[1]
            else:
                converter = converters[0]

            if not converter:
                raise InvalidCodecDefinition(
                    "cannot convert with %r to this direction" % codec_name)

            return converter

        if direction == ENCODE:
            get_func = codecs.getencoder
        else:
            get_func = codecs.getdecoder

        try:
            codec_func = get_func(codec_name)
            return lambda value: codec_func(value)[0]
        except LookupError, error:
            raise InvalidCodecDefinition(error[0])

    def add_to_chain(self, codec_name, direction):
        if codec_name == "pass":
            # "no-operation" codec
            return

        direction = direction or self.default
        if not direction:
            raise InvalidCodecDefinition(
                "coding direction must be defined when no default direction "
                "is specified")

        coder = self.get_coder(codec_name, direction)
        self.chain.append((direction, codec_name, coder))

    def process(self, input_str):
        if not input_str:
            return

        result = input_str
        for direction, codec_name, coder in self.chain:
            try:
                result = coder(result)
            except Exception, error:
                if direction == ENCODE:
                    format_str = "converting value %r to %r failed: %s"
                else:
                    format_str = "converting value %r from %r failed: %s"

                raise ValueError(format_str % (result, codec_name, error[0]))

        return result

