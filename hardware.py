import os
import copy

import numpy as np

import pygame
from pygame import locals as pglocals

from opcodes import *

MSZ_MB = 1024 * 1024
MSZ_KB = 1024
MSZ_B = 8

class Motherboard(object):
	def __init__(self):
		pygame.init()

		self.hdd = HDD(128 * MSZ_MB, self) #Add 128MB HDD

		self.ram = RAM(16 * MSZ_MB, self) #16MB of RAM WOW

		self.monitor = Monitor(self)

		self.cpu = CPU(self, self.ram)
		self.gpu = GPU(self, self.monitor)
		self.io = IO(self)

	def boot(self):
		"""
			This is sort of cheating but copy "biosrom" to ram and execute
			Because we can cheat like this we don't need magic addresses
			  with jump instructions to execute our "bioses". Yay. The CPU
			  just needs to start reading from 0x0
		"""
		pygame.init()

		self.ram.load_file("outputtest.bct")

		self.run_clock()

	def run_clock(self):
		last_tick = pygame.time.get_ticks()
		monitor_refresh = self.monitor.refresh_rate
		cpu = self.cpu
		monitor = self.monitor

		running = True
		while running:
			cpu.execute()

			if pygame.time.get_ticks() - last_tick > monitor_refresh:
				monitor.draw()

			for event in pygame.event.get():
				if event.type == pglocals.QUIT:
					running = False

class Monitor(object):
	"""
		32-Bit addressable memory * resolutionX*resolutionY
		60hz
	"""

	def __init__(self, mobo):
		self.mobo = mobo

		self.resolution = (800, 600)

		self.refresh_rate = 1000/60

		self.screen = pygame.display.set_mode(self.resolution)

		self.screen_buffer = np.zeros(self.resolution)
		self.screen_back_buffer = np.zeros(self.resolution)

		for y in range(600):
			for x in range(800):
				self.screen_buffer[x][y] = (x+y) % 255

	def reset(self):
		del self.screen_buffer
		self.screen_buffer = np.zeros(self.resolution, np.uint32)

	def draw(self):
		pygame.surfarray.blit_array(self.screen, self.screen_buffer)
		pygame.display.flip()

class HDD(object):
	def __init__(self, size, mobo):
		self.mobo = mobo

		self.size = size

		self.root = "fs/"

	def write(self):
		pass

	def read(self):
		pass

class RAM(object):
	def __init__(self, size, mobo = None):
		self.mobo = mobo

		self.size = size

		self.memory = np.zeros(size, dtype=np.uint32)

	def load_file(self, filename):
		#self.memory = np.fromfile(filename, dtype=np.uint32)
		index = 0
		with open(filename, "rb") as f:
			byte = f.read(4)
			while byte:
				self.memory[index] = np.fromstring(byte, '>u4')[0]

				byte = f.read(4)
				index += 1

	def reset(self):
		del self.memory
		self.memory = np.zeros(self.size, dtype=np.uint32)

	def __getitem__(self, item):
		return self.memory[item]

class GPU(object):
	def __init__(self, mobo, monitor):
		self.mobo = mobo
		self.monitor = monitor

		#CHEAT FOR SPEED YAYYY
		#This does mean some weird things for now
		# 1. The amount of RAM is the screen resolution
		# 2. The monitor class technically owns the RAM
		self.ram = self.monitor.screen_back_buffer

		self.x = None
		self.y = None
		self.x2 = None
		self.y2 = None

	def reset(self):
		self.x = None
		self.y = None
		self.x2 = None
		self.y2 = None

	def position(self, x, y):
		self.x = x
		self.y = y

	def select(self, x, y):
		self.x2 = x
		self.y2 = y

		if self.x is None:
			self.x = 0
		if self.y is None:
			self.y = 0

	def set(self, color):
		if self.x is None and self.y is None:
			self.ram[0] = color
			return

		if self.x2 is None or self.y2 is None:
			self.ram[x*y + (x % y)] = color #LOL WRONG
			return

		print("USING COLOR %s" % (hex(int(color))))

		width, height = (self.x2, self.y2)
		data = [color for p in range(width*height)]

		self.fill_buffer(data)

	def fill_buffer(self, data):
		x = self.x if self.x is not None else 0
		y = self.y if self.y is not None else 0
		#This config will be troublesome for large data sets, need to fix
		width = self.x2 if self.x2 is not None else len(data)
		height = self.y2 if self.y is not None else 0

		current_x_offset = 0
		current_y_offset = 0
		for v in data:
			if current_x_offset >= width:
				current_y_offset += 1
				current_x_offset = 0
			if current_y_offset > height:
				#UHOH
				break

			nx = x + current_x_offset
			ny = y + current_y_offset
			self.ram[nx][ny] = v

			current_x_offset += 1

	def flip(self):
		tmp = self.ram
		self.ram = self.monitor.screen_buffer
		self.monitor.screen_buffer = tmp

class CPU(object):
	initial_register_values = {
		R_EAH: 0x0,
		R_EAL: 0x0,
		R_EBH: 0x0,
		R_EBL: 0x0,
		R_ECH: 0x0,
		R_ECL: 0x0,
		R_EDH: 0x0,
		R_EDL: 0x0,

		#Index
		R_SI: 0x0,
		R_DI: 0x0,
		R_BP: 0x0,
		R_SP: 0x0,

		#Program Counter
		R_IP: 0x0,


		R_CS: 0x0,
		R_DS: 0x0,
		R_ES: 0x0,
		R_SS: 0x0
	}

	initial_flags = 0x00000001

	def __init__(self, mobo, ram):
		self.mobo = mobo

		self.ram = ram

		self.reset(initial=True)

	def reset(self, initial=False):
		self.registers = copy.copy(self.initial_register_values)
		self.flags = copy.copy(self.initial_flags)

		if not initial:
			self.ram.reset()

	def get_memory_chunk(self, offset, length):
		actual_offset = self.registers[R_DS] + offset
		return self.ram[actual_offset:actual_offset+length]

	def get_memory(self, offset):
		return self.ram[self.registers[R_DS] + offset]

	def set_memory(self, offset, value):
		self.ram[self.registers[R_DS] + offset] = value

	def push_stack(self, value):
		self.registers[R_SP] += 1
		self.ram[self.registers[R_SS] + self.registers[R_SP]] = value

	def pop_stack(self):
		result = self.ram[self.registers[R_SS] + self.registers[R_SP]]
		self.registers[R_SP] -= 1
		return result

	def execute(self):
		#op_code, *f = list(np.asscalar(self.ram[self.registers[R_CS] + self.registers[R_IP]]).to_bytes(4, byteorder='little', signed=False))
		op_code = self.ram[self.registers[R_CS] + self.registers[R_IP]]

		asz = OPCODE_SIZE[op_code]

		if asz:
			f = self.ram.memory[self.registers[R_CS] + self.registers[R_IP] + 1 : self.registers[R_CS] + self.registers[R_IP] + asz + 1]
		else:
			f = []

		if op_code == 0x00:
			return

		#print(hex(int(op_code)), f, asz)

		self.registers[R_IP] += 1 + asz

		if op_code == 0xA0: #MOV rr
			self.registers[f[0]] = self.registers[f[1]]
		elif op_code == 0xA1: #MOV rm
			self.registers[f[0]] = self.get_memory(f[1])
		elif op_code == 0xA2: #MOVE mr
			self.set_memory(f[0], self.registers[f[1]])
		elif op_code == 0xA3: #MOVE rc
			self.registers[f[0]] = f[1]
		elif op_code == 0xA4: #MOVE mc
			self.set_memory(f[0], f[1])
		elif op_code == 0x20: #ADD rr
			self.registers[f[0]] += self.registers[f[1]]
		elif op_code == 0x21: #ADD rm
			self.registers[f[0]] += self.get_memory(f[1])
		elif op_code == 0x22: #ADD mr
			self.set_memory(f[0], self.get_memory(f[0]) + self.registers[f[1]])
		elif op_code == 0x23: #ADD rc
			self.registers[f[0]] += f[1]
		elif op_code == 0x24: #ADD mc
			self.set_memory(f[0], self.get_memory(f[0]) + f[1])
		elif op_code == 0x29: #SUB rr
			self.registers[f[0]] -= self.registers[f[1]]
		elif op_code == 0x2A: #SUB rm
			self.registers[f[0]] -= self.get_memory(f[1])
		elif op_code == 0x2B: #SUB mr
			self.set_memory(f[0], self.get_memory(f[0]) - self.registers[f[1]])
		elif op_code == 0x2C: #SUB rc
			self.registers[f[0]] -= f[1]
		elif op_code == 0x2D: #SUB mc
			self.set_memory(f[0], self.get_memory(f[0]) - f[1])
		elif op_code == 0xA5: #PUSH r
			self.push_stack(self.registers[f[0]])
		elif op_code == 0xA6: #PUSH m
			self.push_stack(self.get_memory(f[0]))
		elif op_code == 0xA7: #PUSH c
			self.push_stack(f[0])
		elif op_code == 0xA8: #POP r
			self.registers[f[0]] = self.pop_stack()
		elif op_code == 0xA9: #POP m
			self.set_memory(f[0], self.pop_stack())
		elif op_code == 0x1B: #CALL
			self.push_stack(self.registers[R_IP])
			self.registers[R_IP] = f[0]
		elif op_code == 0x1C: #RET
			self.registers[R_IP] = self.pop_stack()
		elif op_code == 0x38: #CMP rr
			pass
		elif op_code == 0x25: #INC r
			self.registers[f[0]] += 1
		elif op_code == 0x26: #INC m
			self.set_memory(f[0], self.get_memory(f[0]) + 1)
		elif op_code == 0x27: #DEC r
			self.registers[f[0]] -= 1
		elif op_code == 0x28: #DEC m
			self.set_memory(f[0], self.get_memory(f[0]) - 1)
		elif op_code == 0xAA: #LEA rm
			self.registers[f[0]] = f[1]
		elif op_code == 0x0B: #JMPC
			self.registers[R_CS] = f[0]
			self.registers[R_IP] = 0

		### BEGIN GFX OPCODES
		elif op_code == 0x43: #GMOV r
			self.mobo.gpu.fill_buffer([self.registers[f[0]]])
		elif op_code == 0x45: #GMOV mm SORT OF LEAISH
			self.mobo.gpu.fill_buffer(self.get_memory_chunk(f[0], self.get_memory(f[1])))
		elif op_code == 0x47: #GMOV mc SORT OF LEAISH
			self.mobo.gpu.fill_buffer(self.get_memory_chunk(f[0], f[1]))
		elif op_code == 0x48: #GPOS rr
			self.mobo.gpu.position(self.registers[f[0]], self.registers[f[1]])
		elif op_code == 0x49: #GPOS rm
			self.mobo.gpu.position(self.registers[f[0]], self.get_memory(f[1]))
		elif op_code == 0x4A: #GPOS mr
			self.mobo.gpu.position(self.get_memory(f[0]), self.registers[f[1]])
		elif op_code == 0x4B: #GPOS mm
			self.mobo.gpu.position(self.get_memory(f[0]), self.get_memory(f[1]))
		elif op_code == 0x4C: #GPOS rc
			self.mobo.gpu.position(self.registers[f[0]], f[1])
		elif op_code == 0x4D: #GPOS mc
			self.mobo.gpu.position(self.get_memory(f[0]), f[1])
		elif op_code == 0x4E: #GPOS cc
			self.mobo.gpu.position(f[0], f[1])
		elif op_code == 0x4F: #GPOS cm
			self.mobo.gpu.position(f[0], self.get_memory(f[1]))
		elif op_code == 0x50: #GPOS cr
			self.mobo.gpu.position(f[0], self.registers[f[1]])
		elif op_code == 0x54: #GSELECT rr
			self.mobo.gpu.select(self.registers[f[0]], self.registers[f[1]])
		elif op_code == 0x55: #GSELECT rm
			self.mobo.gpu.select(self.registers[f[0]], self.get_memory(f[1]))
		elif op_code == 0x56: #GSELECT mr
			self.mobo.gpu.select(self.get_memory(f[0]), self.registers[f[1]])
		elif op_code == 0x57: #GSELECT mm
			self.mobo.gpu.select(self.get_memory(f[0]), self.get_memory(f[0]))
		elif op_code == 0x58: #GSELECT rc
			self.mobo.gpu.select(self.registers[f[0]], f[1])
		elif op_code == 0x59: #GSELECT mc
			self.mobo.gpu.select(self.get_memory(f[0]), f[1])
		elif op_code == 0x5A: #GSELECT cc
			self.mobo.gpu.select(f[0], f[1])
		elif op_code == 0x5B: #GSELECT cm
			self.mobo.gpu.select(f[0], self.get_memory(f[1]))
		elif op_code == 0x5C: #GSELECT cr
			self.mobo.gpu.select(f[0], self.registers[f[1]])
		elif op_code == 0x44: #GRESET
			self.mobo.gpu.reset()
		elif op_code == 0x51: #GSET r
			self.mobo.gpu.set(self.registers[f[0]])
		elif op_code == 0x52: #GSET m
			self.mobo.gpu.set(self.get_memory(f[0]))
		elif op_code == 0x53: #GSET c
			self.mobo.gpu.set(f[0])
		elif op_code == 0x5D: #GFLIP
			self.mobo.gpu.flip()
		#END GFX OPCODES

class IO(object):
	def __init__(self, mobo):
		self.mobo = mobo

class Computer(object):
	def __init__(self):
		self.motherboard = Motherboard()

	def start(self):
		self.motherboard.boot()

	def shutdown(self):
		pass

	def restart(self):
		pass
