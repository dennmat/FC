import re
import struct

from pyparsing import *

from opcodes import *

REGISTERS_MAP = dict(REGISTERS)
LABELS = {}

class Section(object):
	def __init__(self, name):
		self.name = name
		self.offset = 0
		self.stack = []

class Instruction(object):
	def __init__(self, opcode, label=None):
		self.opcode = opcode
		self.params = []
		self.label = label

	def get_param_int(self, param):
		if isinstance(param, Constant):
			if param.type == Constant.BINARY:
				return int(param.value, 2)
			elif param.type == Constant.HEX:
				return int(param.value, 16)
			elif param.type == Constant.DECIMAL:
				return int(param.value)
		else:
			return param.to_int()

	def get_param_rep(self, param):
		if isinstance(param, Constant):
			return 'c'
		elif isinstance(param, MemoryIndex):
			return 'm'
		elif isinstance(param, Register):
			return 'r'
		elif isinstance(param, LabelArg):
			return 'l'

		return 'X'

	def to_bytes(self):
		param_string = ''.join([self.get_param_rep(p) for p in self.params])

		op_m = OPCODE_MAP[self.opcode]

		if isinstance(op_m, dict):
			op_m = op_m[param_string]

		param_bytes = [self.get_param_int(p) for p in self.params]

		return [op_m] + param_bytes

class MemoryIndex(object):
	def __init__(self, label, offset=0):
		self.label = label
		self.offset = offset

	def to_int(self):
		return int(self.offset)

class Register(object):
	def __init__(self, register):
		self.register = register

	def to_int(self):
		return int(REGISTERS_MAP[self.register])

class Constant(object):
	UNDECLARED = 0
	DECIMAL = 10
	BINARY = 2
	HEX = 16

	def __init__(self, type, value):
		self.type = type
		self.value = value

	def __repr__(self):
		t = {
			0: 'N/A',
			10: 'DEC',
			2: 'BIN',
			16: 'HEX'
		}[self.type]

		return "Constant<Type %s>: %s" % (t, self.value)

class OpCode(object):
	def __init__(self, opcode):
		self.str_opcode = opcode

class Declaration(object):
	def __init__(self, name, initial):
		self.name = name
		self.initial = initial

		self.offset = -1

		self.size = len(initial)

class Label(object):
	def __init__(self, name):
		self.name = name
		self.offset = -1

class LabelArg(object):
	def __init__(self, name):
		self.name = name

	def to_int(self):
		for k, v in LABELS.items():
			if k.name == self.name:
				return int(k.offset)
		#TODO ERROR

STACK = []
DATA_SECTION = Section("DATA")
TEXT_SECTION = Section("TEXT")

CURRENT_SECTION = None

def parsedLabel(s, l, t):
	return Label(t[0])

def parsedLabelArg(s, l, t):
	return LabelArg(t[0])

def parsedSection(s, l, t):
	global CURRENT_SECTION
	CURRENT_SECTION = {
		"TEXT": TEXT_SECTION,
		"DATA": DATA_SECTION
	}[t[1]]
	return CURRENT_SECTION

def parsedBinary(s, l, t):
	return Constant(Constant.BINARY, t[0])

def parsedHex(s, l, t):
	return Constant(Constant.HEX, t[0])

def parsedNumber(s, l, t):
	return Constant(Constant.DECIMAL, t[0])

def parsedMemory(s, l, t):
	return MemoryIndex(t[0])

def parsedInstruction(s, l, t):
	label = None
	index_offset = 0
	if isinstance(t[0], Label):
		label = t[0]
		index_offset += 1

	inst = Instruction(t[index_offset],label=label)

	for p in t[1+index_offset:]:
		inst.params.append(p)

	CURRENT_SECTION.stack.append(inst)

	if label is not None:
		LABELS[label] = inst

	return inst

def parsedRegister(s, l, t):
	return Register(t[0])

def parsedDeclaration(s, l, t):
	decl = Declaration(t[0], t[1:])

	CURRENT_SECTION.stack.append(decl)

	return decl

ParserElement.setDefaultWhitespaceChars(' \t')

LBRACK = Suppress('[')
RBRACK = Suppress(']')
COLON = Literal(':')
DATA = Literal('DATA')
TEXT = Literal('TEXT')
COMMA = Suppress(',')
SPACE = Literal('\ ')
OSPACE = Optional(SPACE)
OPCODE = oneOf(' '.join(OPCODE_MAP.keys()))
REGISTER = oneOf(' '.join([r[0] for r in REGISTERS]))
NAME = Word(alphanums)
SEMICOLON = Suppress(';')
DOT = Literal('.')
HEX = CaselessLiteral("0x").suppress() + Word(hexnums)
BINARY = CaselessLiteral("b").suppress() + Word("01")
LABEL = NAME + COLON.suppress()
ARG_NAME = Word(alphanums)
ARG_NAME.setParseAction(parsedLabelArg)

LABEL.setParseAction(parsedLabel)

NUMBER = Word(nums)

LSTART = LineStart().suppress()
LEND = LineEnd().suppress()

comment = SEMICOLON + restOfLine

section = (DOT + DATA + LEND) | (DOT + TEXT + LEND)
section.setParseAction(parsedSection)
mem = LBRACK + NAME + RBRACK
mem.setParseAction(parsedMemory)
BINARY.setParseAction(parsedBinary)
HEX.setParseAction(parsedHex)
NUMBER.setParseAction(parsedNumber)

const = BINARY | HEX | NUMBER

arg = mem | const | REGISTER | ARG_NAME

REGISTER.setParseAction(parsedRegister)

instruction = (Optional(LABEL) + OPCODE + LEND) | (Optional(LABEL) + OPCODE + delimitedList(arg, delim=',') + LEND)
instruction.setParseAction(parsedInstruction)
declaration = NAME + delimitedList(const, delim=',') + LEND
declaration.setParseAction(parsedDeclaration)

stmt = (instruction | section | declaration)

lngg = OneOrMore(Group(stmt) | LEND)
lngg.ignore(comment)
lngg.ignore(LSTART + LEND)

pbody = open('test.mfcasm', 'r').read()

lines = lngg.parseString(pbody)
OPCODES = OPCODE_MAP.keys()
REGISTERS = [r[0] for r in REGISTERS]

print(lines)

print(TEXT_SECTION.stack[0].params)

#Determine data offsets
current_offset = 0
var_map = {}
for decl in DATA_SECTION.stack:
	decl.offset = current_offset
	current_offset += decl.size
	var_map[decl.name] = decl

#Set memory offset for vars!
for inst in TEXT_SECTION.stack:
	if not len(inst.params):
		continue

	for p in inst.params:
		if not isinstance(p, MemoryIndex):
			continue

		p.offset = var_map[p.label].offset

start_offset = 0
#Determine label offsets
# Add 1 to offsets to support injected IP register setting
for lbl, find_inst in LABELS.items():
	for i, inst in enumerate(TEXT_SECTION.stack):
		if inst == find_inst:
			lbl.offset = i
			if lbl.name == 'start':
				start_offset = i

fhndl = open('outputtest.bct', 'wb')
data_block = []
for decl in DATA_SECTION.stack:
	data_block += [int(v.value, v.type) for v in decl.initial]

#Set Offset Registers for CPU
#Working from Memory 0
#The 5 words for the 2 instructions that setup the registers
ds_inst = Instruction('MOV')
ds_inst.params = [Register("DS"), Constant(10, 5)]
cs_inst = Instruction('JMPC')
cs_inst.params = [Constant(10, 5 + len(data_block))] #TODO start_offset still broken

fhndl.write(struct.pack('>3I', *ds_inst.to_bytes()))
fhndl.write(struct.pack('>2I', *cs_inst.to_bytes()))

fhndl.write(struct.pack('>%sI' % len(data_block), *data_block))

for inst in TEXT_SECTION.stack:
	data = inst.to_bytes()
	print(data)
	fhndl.write(struct.pack('>%sI' % len(data), *data))

fhndl.close()
