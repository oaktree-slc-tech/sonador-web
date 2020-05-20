import six, time, zlib

import binascii
from django.core import signing
from django.core.signing import JSONSerializer
from django.utils.crypto import constant_time_compare, salted_hmac


HEX_DEFAULT_ENCODING = 'utf-8'


def hex_encode(s, default_encoding=HEX_DEFAULT_ENCODING):
	'''	Create a hexadecimal encoded string from the provided input
	'''
	# If passed in as number, convert to string
	if isinstance(s, (int, float)):
		s = str(s)

	# If passed as a string, encode to binary
	if isinstance(s, six.string_types):
		s = s.encode(default_encoding)

	if not isinstance(s, six.binary_type):
		raise TypeError('Unable to create signature from provided string, invalid type: %s' % type(s))

	return binascii.hexlify(s).decode()


def hex_decode(s, default_encoding=HEX_DEFAULT_ENCODING):
	'''	Decode a hexeadecimal encoded string from the provided input
	'''
	# If passed as string, encode to binary
	if not isinstance(s, six.string_types):
		s = s.decode(default_encoding)

	return bytes.fromhex(s)


def hex_hmac(salt, value, key):
	return hex_encode(salted_hmac(salt, value, key).digest())


class HexadecimalSigner(signing.TimestampSigner):
	'''	Signer instance that uses hexadecimal signatures instead of Base64 encoded signatures
	'''
	def signature(self, value):
		return hex_hmac(self.salt + 'signer', value, self.key)

	def timestamp(self):
		return hex_encode(int(time.time()))

	def decode_timestamp(self, value, default_encoding=HEX_DEFAULT_ENCODING):
		return int(hex_decode(value))

	def unsign(self, value, max_age=None):
		result = super(signing.TimestampSigner, self).unsign(value)
		value, timestamp = result.rsplit(self.sep, 1)
		timestamp = self.decode_timestamp(timestamp)
		
		if max_age is not None:
			if isinstance(max_age, datetime.timedelta):
				max_age = max_age.total_seconds()
			
			# Check timestamp is not older than max_age
			age = time.time() - timestamp
			if age > max_age:
				raise SignatureExpired(
					'Signature age %s > %s seconds' % (age, max_age))
		
		return value


def dumps(obj, key=None, salt='django.core.signing', serializer=JSONSerializer, compress=False):
	"""
	Return URL-safe, hmac/SHA1 signed base64 compressed JSON string. If key is
	None, use settings.SECRET_KEY instead.

	If compress is True (not the default), check if compressing using zlib can
	save some space. Prepend a '.' to signify compression. This is included
	in the signature, to protect against zip bombs.

	Salt can be used to namespace the hash, so that a signed string is
	only valid for a given namespace. Leaving this at the default
	value or re-using a salt value across different parts of your
	application without good cause is a security risk.

	The serializer is expected to return a bytestring.
	"""
	data = serializer().dumps(obj)

	# Flag for compression
	is_compressed = False

	if compress:
		cdata = zlib.compress(data)

		# Only return compressed data if the compression result is 
		# less than the uncompressed data
		if len(cdata) < (len(data) - 1):
			data = cdata
			is_compressed = True

	# Hex encode the data
	hdata = hex_encode(data)

	# Inidcate that the data is compressed
	if is_compressed:
		hdata = '.'+hdata

	return HexadecimalSigner(key, salt=salt).sign(hdata)


def loads(s, key=None, salt='django.core.signing', serializer=JSONSerializer, max_age=None,
		default_encoding=HEX_DEFAULT_ENCODING):
	"""
	Reverse of dumps(), raise BadSignature if signature fails.

	The serializer is expected to accept a bytestring.
	"""
	# TimestampSigner.unsign() returns str but base64 and zlib compression
	# operate on bytes.
	hdata = HexadecimalSigner(key, salt=salt).unsign(s, max_age=max_age).encode()
	decompress = hdata[:1] == b'.'

	# Determine if data is compressed, if so, remove compression flag
	if decompress:
		hdata = hdata[1:]

	# Decode from hexadecimal
	data = hex_decode(hdata)
	if decompress:
		data = zlib.decompress(data)

	return serializer().loads(data if isinstance(data, six.binary_type) else data.encode(default_encoding))
