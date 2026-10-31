# GreekPlusPlus compiler
#
# Compiles programs written in GreekPlusPlus, a small educational language with
# Greek keywords, to RISC-V assembly. Stages:
#   1. Lexical analysis    -> tokens
#   2. Syntax analysis     -> recursive-descent parser with semantic checks
#   3. Symbol table        -> scopes and offsets, written to <file>.sym
#   4. Intermediate code   -> quadruples, written to <file>.int
#   5. Final code          -> RISC-V assembly, written to <file>.asm
#
# Usage: python compiler.py <source-file>

import sys
import os

MODE_CV = "CV"  # pass by value
MODE_REF = "REF"  # pass by reference
MODE_RET = "RET"  # return value of a function

class Token:
    def __init__(self, recognized_token, token_type, line_number):
        self.recognized_token = recognized_token
        self.token_type = token_type
        self.line_number = line_number

    def __str__(self):
        return f"{self.recognized_token}\t family: {self.token_type}\t Line: {self.line_number}"

# Reserved words of the language
keywords = (
    "πρόγραμμα", "δήλωση", "εάν", "τότε", "αλλιώς", "εάν_τέλος",
    "επανάλαβε", "μέχρι", "όσο", "όσο_τέλος", "για", "έως", "με_βήμα", "για_τέλος",
    "διάβασε", "γράψε", "συνάρτηση", "διαδικασία", "διαπροσωπεία",
    "είσοδος", "έξοδος", "αρχή_συνάρτησης", "τέλος_συνάρτησης",
    "αρχή_διαδικασίας", "τέλος_διαδικασίας", "αρχή_προγράμματος", "τέλος_προγράμματος",
    "ή", "και", "όχι", "εκτέλεσε"
)

# Operators and delimiters
separators = (";", ",")
operations = ("+", "-", "*", "/")
single_corr = ("<", ">", "=")
multi_corr = ("<=", ">=", "<>")
assignment = (":=")
blocks = ("(", ")", "[", "]")
reference = ("%")

MAX_IDENTIFIER_LENGTH = 30

# Raised for lexical, syntax and semantic errors
class CompileError(Exception):
    def __init__(self, message, line_number=None, kind="Syntax"):
        super().__init__(message)
        self.line_number = line_number
        self.kind = kind

    def __str__(self):
        if self.line_number:
            return f"{self.kind} error (line {self.line_number}): {super().__str__()}"
        else:
            return f"{self.kind} error: {super().__str__()}"

# ---------------------------------------------------------------------------
# Lexical analysis
# ---------------------------------------------------------------------------

def lexicalAnalyzer(input_text):
    tokens = []
    i = 0
    line_number = 1

    while i < len(input_text):
        c = input_text[i]

        if c == ' ' or c == '\t':
            i += 1
            continue

        if c == '\n':
            line_number += 1
            i += 1
            continue

        # Comments are enclosed in { } and may be nested
        if c == "{":
            comment_start_line = line_number
            i += 1
            nesting_level = 1

            while i < len(input_text):
                if input_text[i] == "{":
                    nesting_level += 1
                elif input_text[i] == "}":
                    nesting_level -= 1
                    if nesting_level == 0:
                        i += 1
                        break

                if input_text[i] == '\n':
                    line_number += 1
                i += 1
            else:
                raise CompileError(f"Unclosed comment starting on line {comment_start_line}", comment_start_line, "Lexical")
            continue

        # Two-character operators: <=, >=, <>, :=
        if i + 1 < len(input_text):
            maybe_two = input_text[i:i+2]

            if maybe_two in multi_corr:
                tokens.append(Token(maybe_two, 'CORRELATION', line_number))
                i += 2
                continue

            if maybe_two in assignment:
                tokens.append(Token(maybe_two, 'ASSIGNMENT', line_number))
                i += 2
                continue

        if c in operations:
            tokens.append(Token(c, 'OPERATOR', line_number))
            i += 1
            continue

        if c in single_corr:
            tokens.append(Token(c, 'CORRELATION', line_number))
            i += 1
            continue

        if c in blocks:
            tokens.append(Token(c, 'BLOCK', line_number))
            i += 1
            continue

        if c in separators:
            tokens.append(Token(c, 'SEPARATOR', line_number))
            i += 1
            continue

        if c in reference:
            tokens.append(Token(c, 'REFERENCE', line_number))
            i += 1
            continue

        # Integer constants
        if c.isdigit() :
            token_str = c
            i += 1

            while i < len(input_text) and input_text[i].isdigit():
                token_str += input_text[i]
                i += 1
            tokens.append(Token(token_str, 'NUMBER', line_number))
            continue

        # Identifiers and keywords (Latin or Greek letters, digits, underscore)
        if c.isalpha() :
            token_str = c
            i += 1

            while i < len(input_text):
                ch = input_text[i]

                if ch.isalnum() or ch == '_':
                    token_str += ch
                    i += 1
                else:
                    break

            if len(token_str) > MAX_IDENTIFIER_LENGTH:
                raise CompileError(f"Identifier '{token_str[:MAX_IDENTIFIER_LENGTH]}...' exceeds max length {MAX_IDENTIFIER_LENGTH}", line_number, "Lexical")

            if token_str in keywords:
                tokens.append(Token(token_str, 'KEYWORD', line_number))
            else :
                tokens.append(Token(token_str, 'IDENTIFIER', line_number))

            continue

        raise CompileError(f"Invalid character '{c}'", line_number, "Lexical")
    return tokens

# ---------------------------------------------------------------------------
# Symbol table
# ---------------------------------------------------------------------------

class Entity:
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"Entity(Name: {self.name})"

class ArgumentInfo:
    def __init__(self, name, arg_type, mode):
        self.name = name
        self.type = arg_type
        self.mode = mode

    def __str__(self):
        return f"Arg(Name: {self.name}, Type: {self.type}, Mode: {self.mode})"

class VariableEntity(Entity):
    def __init__(self, name, var_type, offset):
        super().__init__(name)
        self.type = var_type
        self.offset = offset

    def __str__(self):
        return f"Variable(Name: {self.name}, Type: {self.type}, Offset: {self.offset})"

class FunctionEntity(Entity):
    def __init__(self, name, return_type):
        super().__init__(name)
        self.type = return_type
        self.start_quad = 0
        self.argument_list = []
        self.framelength = 0
        self.nesting_level = 0

    def add_argument(self, arg_info: ArgumentInfo):
        self.argument_list.append(arg_info)

    def __str__(self):
         args_str = ', '.join(map(str, self.argument_list))
         return (f"Function(Name: {self.name}, Type: {self.type}, StartQuad: {self.start_quad}, "
                 f"FrameLen: {self.framelength}, Level: {self.nesting_level}, Args: [{args_str}])")

class ProcedureEntity(FunctionEntity):
     def __init__(self, name):
         super().__init__(name, return_type="void")

     def __str__(self):
         args_str = ', '.join(map(str, self.argument_list))
         return (f"Procedure(Name: {self.name}, StartQuad: {self.start_quad}, "
                 f"FrameLen: {self.framelength}, Level: {self.nesting_level}, Args: [{args_str}])")

class ParameterEntity(Entity):
    def __init__(self, name, param_type, mode, offset):
        super().__init__(name)
        self.type = param_type
        self.mode = mode
        self.offset = offset

    def __str__(self):
        return f"Parameter(Name: {self.name}, Type: {self.type}, Mode: {self.mode}, Offset: {self.offset})"

class TemporaryEntity(Entity):
    def __init__(self, name, temp_type, offset):
        super().__init__(name)
        self.type = temp_type
        self.offset = offset

    def __str__(self):
        return f"Temporary(Name: {self.name}, Type: {self.type}, Offset: {self.offset})"

# Every scope starts at offset 12: return address, access link, return value
class Scope:
    INITIAL_OFFSET = 12

    def __init__(self, nesting_level):
        self.entities = []
        self.nesting_level = nesting_level
        self.current_offset = self.INITIAL_OFFSET

    def add_entity(self, entity):
        for existing_entity in self.entities:
            if existing_entity.name == entity.name:
                raise ValueError(f"Redeclaration of '{entity.name}'")
        self.entities.append(entity)

    def allocate_offset(self, size=4):
         offset = self.current_offset
         self.current_offset += size
         return offset

    def __str__(self):
        if self.entities:
            ents = ""
            for entity in self.entities:
                ents += "  " + str(entity) + "\n"
            ents = ents.rstrip()
        else:
            ents = "  <empty>"

        return f"Scope(Level: {self.nesting_level}, Next Offset: {self.current_offset}):\n  {ents}"


class SymbolTable:
    def __init__(self):
        self.scope_stack= []
        self.current_level = -1
        self.add_scope()
        self.sym_info = []
        self.closed_scopes = []
        self.current_line = None  # updated by the parser, used in error messages


    def add_scope(self):
        self.current_level += 1
        new_scope = Scope(self.current_level)
        self.scope_stack.append(new_scope)

    def remove_scope(self):
        if not self.scope_stack:
            raise IndexError("Error: Cannot remove scope from empty symbol table.")
        exiting_scope = self.scope_stack.pop()
        self.closed_scopes.append(exiting_scope)

        self.sym_info.append(f"--- Scope Level {exiting_scope.nesting_level} ---\n")
        self.sym_info.append(str(exiting_scope) + "\n")
        self.sym_info.append("--------------------\n")

        self.current_level -= 1
        return exiting_scope.current_offset

    def finalize_symbol_table(self):
        if self.scope_stack:
            final_scope = self.scope_stack[0]
            self.sym_info.append(f"--- Scope Level {final_scope.nesting_level} ---\n")
            self.sym_info.append(str(final_scope) + "\n")
            self.sym_info.append("--------------------\n")

    def write_sym_file(self, filename="symbol_table.sym"):
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("".join(self.sym_info))
        except IOError as e:
            print(f"Error writing symbol table to file: {e}")

    def insert_entity(self, entity: Entity):
        if not self.scope_stack:
            raise IndexError("Error: Symbol table has no active scope.")
        try:
            self.scope_stack[-1].add_entity(entity)
        except ValueError as e:
            raise CompileError(str(e), self.current_line, "Semantic")

    def lookup(self, name):
        if not self.scope_stack:
            return None

        for scope in reversed(self.scope_stack):
            for entity in scope.entities:
                if entity.name == name:
                    return entity
        return None

    def get_current_scope(self):
         if self.scope_stack:
             return self.scope_stack[-1]
         return None

    def get_current_nesting_level(self):
         return self.current_level

    def __str__(self):
        s = "--- Symbol Table ---\n"
        if not self.scope_stack: s+= "<Empty>\n"
        for i, scope in enumerate(self.scope_stack):
             s += f" Stack index {i}:\n{scope}\n"
        s += "--------------------\n"
        return s


# ---------------------------------------------------------------------------
# Intermediate code (quadruples)
# ---------------------------------------------------------------------------

class Quad:

    def __init__(self, label, op, x, y, z):
        self.label = label
        self.op = op
        self.x = x
        self.y = y
        self.z = z

    def __str__(self):
        return f"{self.label}: {self.op}, {self.x}, {self.y}, {self.z}"

    # Fills in the jump target of an incomplete quad (used by backpatching)
    def set_target(self, target_label):
        if self.z == '_':
            self.z = target_label

class IntermediateCodeGenerator:

    def __init__(self, symbol_table: SymbolTable):
        self.quads = []
        self.quad_label = 1
        self.temp_counter = 0
        self.symbol_table = symbol_table

    def nextquad(self):
        return self.quad_label

    def genquad(self, op, x, y, z):

        x_ = x or "_"
        y_ = y or "_"
        z_ = z or "_"

        new_quad = Quad(self.quad_label, op, x_, y_, z_)
        self.quads.append(new_quad)
        self.quad_label += 1

    # Creates a new temporary variable (T@1, T@2, ...) and adds it to the symbol table
    def newtemp(self, temp_type="integer"):

        temp_name = f"T@{self.temp_counter + 1}"
        self.temp_counter += 1

        current_scope = self.symbol_table.get_current_scope()
        if current_scope:
            offset = current_scope.allocate_offset()
            temp_entity = TemporaryEntity(temp_name, temp_type, offset)
            self.symbol_table.insert_entity(temp_entity)
        else:
            print(f"Warning: Cannot add temporary '{temp_name}', no current scope.")

        return temp_name

    def emptylist(self):
        return []

    def makelist(self, label):
        return [label]

    def mergelist(self, list1, list2):
        return list1 + list2

    def backpatch(self, list_of_labels, z):
        for label in list_of_labels:
            if isinstance(label, int) and 1 <= label <= len(self.quads):
                quad_index = label - 1
                self.quads[quad_index].set_target(z)
            else:
                print(f"Error: Invalid label '{label}' (type {type(label)}) requested for backpatching to {z}.")

    def print_quads(self, filename="intermediate.int"):
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                for quad in self.quads:
                    f.write(str(quad) + "\n")
        except IOError as e:
            print(f"Error writing intermediate code to file {filename}: {e}")

# ---------------------------------------------------------------------------
# Final code generation (RISC-V assembly)
# ---------------------------------------------------------------------------

class FinalCode:
    # Stack layout of an activation record (offsets are subtracted from sp):
    #   0(sp)   return address
    #   -4(sp)  access link (sp of the statically enclosing routine)
    #   -8(sp)  address where a function stores its return value
    #   -12(sp) and below: parameters, local variables, temporaries
    # Globals are accessed through gp, which points to the main program's frame.

    arith = {"+": "add", "-": "sub", "*": "mul", "/": "div"}
    logic = {"=": "beq", "<>": "bne", "<": "blt", ">": "bgt",
             "<=": "ble", ">=": "bge"}

    def __init__(self, icg, st):
        self.icg = icg
        self.st = st
        self.q = icg.quads
        self.asm = []

        self.par_phase = False
        self.par_cnt = 0

        # Scopes visible in the routine being generated (global scope first)
        self.global_scope = st.scope_stack[0]
        self.scope_chain = [self.global_scope]

        # Every function/procedure, indexed by the label of its begin_block quad
        self.routines = {}
        for scope in st.closed_scopes + st.scope_stack:
            for ent in scope.entities:
                if isinstance(ent, FunctionEntity):
                    self.routines[ent.start_quad] = ent

    def produce(self, line):
        self.asm.append(line)

    def label(self, q):
        self.produce(f"L{q.label}:")

    def cur_level(self):
        return len(self.scope_chain) - 1

    def cur_frame(self):
        return self.scope_chain[-1].current_offset

    def _scope_entity(self, name):
        # Static scoping: search the current routine first, then its enclosing routines
        for scope in reversed(self.scope_chain):
            for ent in scope.entities:
                if ent.name == name:
                    return scope, ent
        raise ValueError(f"Final code: unknown name '{name}'")

    def _is_global(self, scope):
        return scope.nesting_level == 0

    def _is_ref(self, ent):
        return getattr(ent, "mode", "") == MODE_REF

    def gnlvcode(self, v):
        # Loads into t0 the address of a non-local variable, following access links
        scope, ent = self._scope_entity(v)
        level_diff = self.cur_level() - scope.nesting_level

        self.produce("\t\tlw t0, -4(sp)")
        for _ in range(level_diff - 1):
            self.produce("\t\tlw t0, -4(t0)")
        self.produce(f"\t\taddi t0, t0, -{ent.offset}")

    def loadvr(self, v, reg):
        # Loads the value of variable/constant v into register reg
        if v.isdigit():
            self.produce(f"\t\tli {reg}, {v}")
            return
        scope, ent = self._scope_entity(v)
        is_ref = self._is_ref(ent)

        if scope.nesting_level == self.cur_level():
            if is_ref:
                self.produce(f"\t\tlw t0, -{ent.offset}(sp)")
                self.produce(f"\t\tlw {reg}, (t0)")
            else:
                self.produce(f"\t\tlw {reg}, -{ent.offset}(sp)")
        elif self._is_global(scope):
            self.produce(f"\t\tlw {reg}, -{ent.offset}(gp)")
        else:
            self.gnlvcode(v)
            if is_ref:
                self.produce("\t\tlw t0, (t0)")
            self.produce(f"\t\tlw {reg}, (t0)")

    def storerv(self, reg, v):
        # Stores register reg into variable v
        scope, ent = self._scope_entity(v)
        is_ref = self._is_ref(ent)

        if scope.nesting_level == self.cur_level():
            if is_ref:
                self.produce(f"\t\tlw t0, -{ent.offset}(sp)")
                self.produce(f"\t\tsw {reg}, (t0)")
            else:
                self.produce(f"\t\tsw {reg}, -{ent.offset}(sp)")
        elif self._is_global(scope):
            self.produce(f"\t\tsw {reg}, -{ent.offset}(gp)")
        else:
            self.gnlvcode(v)
            if is_ref:
                self.produce("\t\tlw t0, (t0)")
            self.produce(f"\t\tsw {reg}, (t0)")

    def gen_assign(self, q):
        self.label(q)
        self.loadvr(q.x, "t1")
        self.storerv("t1", q.z)

    def gen_arith(self, q):
        self.label(q)
        self.loadvr(q.x, "t1")
        self.loadvr(q.y, "t2")
        self.produce(f"\t\t{self.arith[q.op]} t1, t1, t2")
        self.storerv("t1", q.z)

    def gen_logic(self, q):
        self.label(q)
        self.loadvr(q.x, "t1")
        self.loadvr(q.y, "t2")
        self.produce(f"\t\t{self.logic[q.op]} t1, t2, L{q.z}")

    def gen_jump(self, q):
        self.label(q)
        self.produce(f"\t\tj L{q.z}")

    def gen_begin(self, q):
        if q.label in self.routines:
            self.scope_chain = self.routines[q.label].scope_chain
            self.produce(f"# {q.x}")
            self.label(q)
            self.produce("\t\tsw ra, (sp)")
        else:
            self.scope_chain = [self.global_scope]
            self.produce("main:")
            self.label(q)
            self.produce(f"\t\taddi sp, sp, -{self.cur_frame()}")
            self.produce("\t\tmv gp, sp")

    def gen_end(self, q):
        self.label(q)
        if self.cur_level() > 0:
            self.produce("\t\tlw ra, (sp)")
            self.produce("\t\tjr ra")

    def _start_call(self):
        # fp points to the frame the callee will use, right below the caller's frame
        if not self.par_phase:
            self.produce(f"\t\taddi fp, sp, -{self.cur_frame()}")
            self.par_phase = True
            self.par_cnt = 0

    def gen_par(self, q):
        self.label(q)
        self._start_call()

        mode = q.y.upper()

        if mode == MODE_CV:
            self.loadvr(q.x, "t0")
            d = 12 + self.par_cnt * 4
            self.produce(f"\t\tsw t0, -{d}(fp)")
            self.par_cnt += 1

        elif mode == MODE_REF:
            scope, ent = self._scope_entity(q.x)
            is_ref_here = self._is_ref(ent)

            if scope.nesting_level == self.cur_level():
                if is_ref_here:
                    self.produce(f"\t\tlw t0, -{ent.offset}(sp)")
                else:
                    self.produce(f"\t\taddi t0, sp, -{ent.offset}")
            elif self._is_global(scope):
                self.produce(f"\t\taddi t0, gp, -{ent.offset}")
            else:
                self.gnlvcode(q.x)
                if is_ref_here:
                    self.produce("\t\tlw t0, (t0)")
            d = 12 + self.par_cnt * 4
            self.produce(f"\t\tsw t0, -{d}(fp)")
            self.par_cnt += 1

        elif mode == MODE_RET:
            scope, ent = self._scope_entity(q.x)
            self.produce(f"\t\taddi t0, sp, -{ent.offset}")
            self.produce("\t\tsw t0, -8(fp)")

    def gen_call(self, q):
        self.label(q)
        self._start_call()

        callee_scope, callee = self._scope_entity(q.x)

        # Access link: the callee's enclosing routine is found by following
        # (caller level - callee declaration level) links from the caller
        if callee.nesting_level == self.cur_level():
            self.produce("\t\tsw sp, -4(fp)")
        else:
            self.produce("\t\tlw t0, -4(sp)")
            for _ in range(self.cur_level() - callee.nesting_level - 1):
                self.produce("\t\tlw t0, -4(t0)")
            self.produce("\t\tsw t0, -4(fp)")

        frame = self.cur_frame()
        self.produce(f"\t\taddi sp, sp, -{frame}")
        self.produce(f"\t\tjal L{callee.start_quad}")
        self.produce(f"\t\taddi sp, sp, {frame}")

        self.par_phase = False
        self.par_cnt = 0

    def gen_ret(self, q):
        self.label(q)
        self.loadvr(q.x, "t1")
        self.produce("\t\tlw t0, -8(sp)")
        self.produce("\t\tsw t1, (t0)")

    def gen_in(self, q):
        self.label(q)
        self.produce("\t\tli a7, 5")
        self.produce("\t\tecall")
        self.storerv("a0", q.x)

    def gen_out(self, q):
        # Prints the integer followed by a newline
        self.label(q)
        self.loadvr(q.x, "a0")
        self.produce("\t\tli a7, 1")
        self.produce("\t\tecall")
        self.produce("\t\tli a0, 10")
        self.produce("\t\tli a7, 11")
        self.produce("\t\tecall")

    def gen_halt(self, q):
        self.label(q)
        self.produce("\t\tli a0, 0")
        self.produce("\t\tli a7, 93")
        self.produce("\t\tecall")

    def generate_code(self):
        # Translates every quad to RISC-V instructions
        self.produce("L0:")
        self.produce("\t\tj main")

        handlers = {
            ":=": self.gen_assign, "jump": self.gen_jump,
            "begin_block": self.gen_begin, "end_block": self.gen_end,
            "par": self.gen_par, "call": self.gen_call,
            "retv": self.gen_ret, "halt": self.gen_halt,
            "in": self.gen_in, "out": self.gen_out,
        }
        for q in self.q:
            if q.op in handlers:
                handlers[q.op](q)
            elif q.op in self.arith:
                self.gen_arith(q)
            else:
                self.gen_logic(q)

    def save(self, basename):
        with open(basename + ".asm", "w", encoding="utf-8") as f:
            f.write("\n".join(self.asm) + "\n")


# ---------------------------------------------------------------------------
# Syntax analysis: recursive-descent parser, one method per grammar rule.
# Performs semantic checks and generates intermediate code while parsing.
# ---------------------------------------------------------------------------

class SyntaxAnalyzer:

    def __init__(self, tokens):
        self.tokens = tokens
        self.token_index = -1
        self.token = None
        self.st = SymbolTable()
        self.icg = IntermediateCodeGenerator(self.st)
        self.current_subprogram_entity = None

    def nextToken(self):
        self.token_index += 1
        if self.token_index < len(self.tokens):
            self.token = self.tokens[self.token_index]
        else:
            self.token = Token("EOF", "EOF", self.tokens[-1].line_number if self.tokens else 1)
        self.st.current_line = self.token.line_number

    def _syntax_error(self, expected):
        if self.token:
            got = f"'{self.token.recognized_token}' ({self.token.token_type})"
            line = self.token.line_number if self.token.token_type != "EOF" else None
        else:
            got = "end of file"
            line = None
        raise CompileError(f"Expected {expected}, got {got}", line, "Syntax")

    def _semantic_error(self, message):
        line = self.token.line_number if self.token and self.token.token_type != "EOF" else None
        raise CompileError(message, line, "Semantic")


    # Entry point: parses the program and writes the .sym, .int and .asm files
    def program(self, filename):
        self.current_subprogram_entity = None
        self.nextToken()

        if self.token.recognized_token != "πρόγραμμα":
            self._syntax_error("'πρόγραμμα'")
        self.nextToken()

        if self.token.token_type != "IDENTIFIER":
            self._syntax_error("program name (IDENTIFIER)")

        program_name = self.token.recognized_token
        self.nextToken()

        self.programBlock(program_name)

        if self.token.token_type != "EOF":
            self._syntax_error("end of program after main block")

        base_filename = os.path.splitext(filename)[0]

        self.st.finalize_symbol_table()
        self.st.write_sym_file(f"{base_filename}.sym")

        self.icg.print_quads(f"{base_filename}.int")

        fc = FinalCode(self.icg, self.st)
        fc.generate_code()
        fc.save(base_filename)

        self.current_subprogram_entity = None


    def programBlock(self, block_name):

        self.declarations()
        self.subprograms()

        if self.token.recognized_token != "αρχή_προγράμματος":
            self._syntax_error("'αρχή_προγράμματος'")

        self.icg.genquad("begin_block", block_name, "_", "_")
        self.nextToken()
        self.sequence()

        if self.token.recognized_token != "τέλος_προγράμματος":
            self._syntax_error("'τέλος_προγράμματος'")

        self.icg.genquad("halt", "_", "_", "_")
        self.icg.genquad("end_block", block_name, "_", "_")
        self.nextToken()


    def declarations(self):

        while self.token.recognized_token == "δήλωση":
            self.nextToken()
            self.varlist(is_parameter=False)

    def varlist(self, is_parameter=False, param_mode=MODE_CV, func_proc_entity=None):

         if self.token.token_type != "IDENTIFIER":
             self._syntax_error("IDENTIFIER in declaration/parameter list")

         ids_to_process = []
         ids_to_process.append((self.token.recognized_token, self.token.line_number))
         self.nextToken()

         while self.token.recognized_token == ",":
             self.nextToken()
             if self.token.token_type != "IDENTIFIER":
                 self._syntax_error("IDENTIFIER after ','")
             ids_to_process.append((self.token.recognized_token, self.token.line_number))
             self.nextToken()

         current_scope = self.st.get_current_scope()
         if not current_scope:
             self._semantic_error("No active scope for declaration!")

         for name, line in ids_to_process:
             self.st.current_line = line
             offset = current_scope.allocate_offset()
             entity_type = "integer"

             if is_parameter:
                 if func_proc_entity is None:
                     self._semantic_error("Internal error: Parameter declared outside function/procedure context.")
                 entity = ParameterEntity(name, entity_type, param_mode, offset)
                 self.st.insert_entity(entity)
                 func_proc_entity.add_argument(ArgumentInfo(name, entity_type, param_mode))
             else:
                 entity = VariableEntity(name, entity_type, offset)
                 self.st.insert_entity(entity)


    def subprograms(self):
        while self.token.recognized_token in ("συνάρτηση", "διαδικασία"):
            if self.token.recognized_token == "συνάρτηση":
                self.func()
            elif self.token.recognized_token == "διαδικασία":
                self.proc()

    def func(self):

        if self.token.recognized_token != "συνάρτηση":
            self._syntax_error("'συνάρτηση'")
        self.nextToken()

        if self.token.token_type != "IDENTIFIER":
            self._syntax_error("function name (IDENTIFIER)")

        name = self.token.recognized_token
        function_entity = FunctionEntity(name, "integer")
        function_entity.nesting_level = self.st.get_current_nesting_level()

        try:
            self.st.insert_entity(function_entity)
        except ValueError as e:
            self._semantic_error(str(e))

        self.nextToken()
        if self.token.recognized_token != "(":
            self._syntax_error("'(' after function name")
        self.nextToken()

        self.st.add_scope()
        function_entity.scope_chain = list(self.st.scope_stack)
        self.current_subprogram_entity = function_entity

        self.formalparlist(function_entity)

        if self.token.recognized_token != ")":
            self._syntax_error("')' after formal parameters")
        self.nextToken()

        self.funcblock(function_entity)

    def proc(self):

        if self.token.recognized_token != "διαδικασία":
            self._syntax_error("'διαδικασία'")
        self.nextToken()

        if self.token.token_type != "IDENTIFIER":
            self._syntax_error("procedure name (IDENTIFIER)")

        name = self.token.recognized_token
        procedure_entity = ProcedureEntity(name)
        procedure_entity.nesting_level = self.st.get_current_nesting_level()

        try:
            self.st.insert_entity(procedure_entity)
        except ValueError as e:
            self._semantic_error(str(e))

        self.nextToken()
        if self.token.recognized_token != "(":
            self._syntax_error("'(' after procedure name")
        self.nextToken()

        self.st.add_scope()
        procedure_entity.scope_chain = list(self.st.scope_stack)
        self.current_subprogram_entity = procedure_entity

        self.formalparlist(procedure_entity)

        if self.token.recognized_token != ")":
            self._syntax_error("')' after formal parameters")
        self.nextToken()

        self.procblock(procedure_entity)

    def formalparlist(self, func_proc_entity):

        if self.token.token_type == "IDENTIFIER":
            self.varlist(is_parameter=True, func_proc_entity=func_proc_entity)

    def funcblock(self, func_entity):

        if self.token.recognized_token != "διαπροσωπεία":
            self._syntax_error("'διαπροσωπεία'")

        self.nextToken()

        self.funcinput(func_entity)
        self.funcoutput(func_entity)
        self.declarations()
        self.subprograms()
        self.current_subprogram_entity = func_entity

        func_entity.start_quad = self.icg.nextquad()
        self.icg.genquad("begin_block", func_entity.name, "_", "_")

        if self.token.recognized_token != "αρχή_συνάρτησης":
            self._syntax_error("'αρχή_συνάρτησης'")
        self.nextToken()

        self.sequence()

        if self.token.recognized_token != "τέλος_συνάρτησης":
            self._syntax_error("'τέλος_συνάρτησης'")

        func_entity.framelength = self.st.get_current_scope().current_offset

        self.icg.genquad("end_block", func_entity.name, "_", "_")

        self.st.remove_scope()
        self.current_subprogram_entity = None
        self.nextToken()

    def procblock(self, proc_entity):

        if self.token.recognized_token != "διαπροσωπεία":
            self._syntax_error("'διαπροσωπεία'")

        self.nextToken()

        self.funcinput(proc_entity)
        self.funcoutput(proc_entity)
        self.declarations()
        self.subprograms()
        self.current_subprogram_entity = proc_entity

        proc_entity.start_quad = self.icg.nextquad()
        self.icg.genquad("begin_block", proc_entity.name, "_", "_")

        if self.token.recognized_token != "αρχή_διαδικασίας":
            self._syntax_error("'αρχή_διαδικασίας'")
        self.nextToken()

        self.sequence()

        if self.token.recognized_token != "τέλος_διαδικασίας":
            self._syntax_error("'τέλος_διαδικασίας'")

        proc_entity.framelength = self.st.get_current_scope().current_offset

        self.icg.genquad("end_block", proc_entity.name, "_", "_")

        self.st.remove_scope()
        self.current_subprogram_entity = None
        self.nextToken()

    # "είσοδος" lists the parameters passed by value
    def funcinput(self, func_proc_entity):

        if self.token.recognized_token == "είσοδος":
            self.nextToken()
            if self.token.token_type != "IDENTIFIER":
                self._syntax_error("IDENTIFIER after 'είσοδος'")

            names = []
            names.append(self.token.recognized_token)
            self.nextToken()

            while self.token.recognized_token == ",":
                self.nextToken()
                if self.token.token_type != "IDENTIFIER":
                    self._syntax_error("IDENTIFIER after ','")
                names.append(self.token.recognized_token)
                self.nextToken()

            for name in names:
                 entity = self.st.lookup(name)
                 if isinstance(entity, ParameterEntity):
                     entity.mode = MODE_CV
                     for arg_info in func_proc_entity.argument_list:
                         if arg_info.name == name:
                            arg_info.mode = MODE_CV
                            break
                 else:
                      self._semantic_error(f"'{name}' in 'είσοδος' list is not a parameter of {func_proc_entity.name}")

    # "έξοδος" lists the parameters passed by reference
    def funcoutput(self, func_entity):

        if self.token.recognized_token == "έξοδος":
            self.nextToken()

            if self.token.token_type != "IDENTIFIER":
                self._syntax_error("IDENTIFIER after 'έξοδος'")

            names = []
            names.append(self.token.recognized_token)
            self.nextToken()

            while self.token.recognized_token == ",":
                self.nextToken()
                if self.token.token_type != "IDENTIFIER":
                    self._syntax_error("IDENTIFIER after ','")
                names.append(self.token.recognized_token)
                self.nextToken()

            if isinstance(func_entity, ProcedureEntity):
                for name in names:
                     entity = self.st.lookup(name)
                     if isinstance(entity, ParameterEntity):
                         entity.mode = MODE_REF
                         for arg_info in func_entity.argument_list:
                             if arg_info.name == name:
                                arg_info.mode = MODE_REF
                                break
                     else:
                          self._semantic_error(f"'{name}' in 'έξοδος' list is not a parameter of procedure {func_entity.name}")

            elif isinstance(func_entity, FunctionEntity):
                 if len(names) > 0:
                     for name in names:
                        entity = self.st.lookup(name)
                        if isinstance(entity, ParameterEntity):
                            entity.mode = MODE_REF
                            for arg_info in func_entity.argument_list:
                                if arg_info.name == name:
                                    arg_info.mode = MODE_REF
                                    break
                        else:
                            self._semantic_error(f"'{name}' in 'έξοδος' list is not a parameter of function {func_entity.name}")

    def sequence(self):

        self.statement()

        while self.token.recognized_token == ";":
            self.nextToken()
            if self.token.token_type == "EOF" or self.token.recognized_token in (
                "τέλος_προγράμματος", "τέλος_συνάρτησης", "τέλος_διαδικασίας",
                "εάν_τέλος", "όσο_τέλος", "για_τέλος", "μέχρι", "αλλιώς", "}"):
                break
            self.statement()

    def statement(self):

        if self.token.token_type == "IDENTIFIER":
            self.assignment_stat()
        elif self.token.recognized_token == "εάν":
            self.if_stat()
        elif self.token.recognized_token == "όσο":
            self.while_stat()
        elif self.token.recognized_token == "επανάλαβε":
             self.do_stat()
        elif self.token.recognized_token == "για":
            self.for_stat()
        elif self.token.recognized_token == "διάβασε":
            self.input_stat()
        elif self.token.recognized_token == "γράψε":
            self.print_stat()
        elif self.token.recognized_token == "εκτέλεσε":
            self.call_stat()

    def assignment_stat(self):

        if self.token.token_type != "IDENTIFIER":
            self._syntax_error("IDENTIFIER in assignment")

        target_id = self.token.recognized_token
        target_line = self.token.line_number
        target_entity = self.st.lookup(target_id)
        if target_entity is None:
             self._semantic_error(f"Assignment target '{target_id}' is undeclared")

        is_return_assignment = False
        if isinstance(target_entity, FunctionEntity) and \
           self.current_subprogram_entity is not None and \
           target_entity.name == self.current_subprogram_entity.name:
            if self.st.get_current_nesting_level() == target_entity.nesting_level + 1:
                 is_return_assignment = True
                 if target_entity.type == "void":
                     self._semantic_error(f"Internal error: Trying to assign return value to procedure '{target_id}'?")
            else:
                 self._semantic_error(f"Cannot assign to function '{target_id}' from outside its body or from a nested function.")

        self.nextToken()
        if self.token.recognized_token != ":=":
            self._syntax_error("':=' in assignment")
        self.nextToken()

        source_place = self.expression()

        if is_return_assignment:
             self.icg.genquad("retv", source_place, "_", "_")
        elif isinstance(target_entity, (VariableEntity, ParameterEntity, TemporaryEntity)):
            if isinstance(target_entity, ParameterEntity) and target_entity.mode == MODE_CV:
                print(f"Warning (Line {target_line}): Assigning to 'in' (CV) parameter '{target_id}'. Change will be local.")
            self.icg.genquad(":=", source_place, "_", target_id)
        else:
             self._semantic_error(f"Cannot assign to '{target_id}' (it's a {type(target_entity).__name__} or assignment is invalid in this context)")

    def if_stat(self):

        if self.token.recognized_token != "εάν":
            self._syntax_error("'εάν'")
        self.nextToken()

        B_true, B_false = self.condition()

        if self.token.recognized_token != "τότε":
            self._syntax_error("'τότε'")
        self.nextToken()

        self.icg.backpatch(B_true, self.icg.nextquad())

        self.sequence()

        jump_list_after_then = self.icg.emptylist()
        if self.token.recognized_token == "αλλιώς":
            jump_list_after_then = self.icg.makelist(self.icg.nextquad())
            self.icg.genquad("jump", "_", "_", "_")

        self.elsepart(B_false)

        if jump_list_after_then:
            self.icg.backpatch(jump_list_after_then, self.icg.nextquad())

        if self.token.recognized_token != "εάν_τέλος":
            self._syntax_error("'εάν_τέλος'")
        self.nextToken()

    def elsepart(self, B_false_list):

        if self.token.recognized_token == "αλλιώς":
            self.icg.backpatch(B_false_list, self.icg.nextquad())
            self.nextToken()
            self.sequence()
            return True
        else:
            self.icg.backpatch(B_false_list, self.icg.nextquad())
            return False

    def while_stat(self):

        if self.token.recognized_token != "όσο":
            self._syntax_error("'όσο'")
        self.nextToken()

        B_quad = self.icg.nextquad()
        B_true, B_false = self.condition()

        if self.token.recognized_token != "επανάλαβε":
            self._syntax_error("'επανάλαβε'")
        self.nextToken()

        self.icg.backpatch(B_true, self.icg.nextquad())

        self.sequence()

        self.icg.genquad("jump", "_", "_", B_quad)
        self.icg.backpatch(B_false, self.icg.nextquad())

        if self.token.recognized_token != "όσο_τέλος":
            self._syntax_error("'όσο_τέλος'")
        self.nextToken()

    def do_stat(self):

        if self.token.recognized_token != "επανάλαβε":
            self._syntax_error("'επανάλαβε'")
        self.nextToken()

        S_quad = self.icg.nextquad()

        self.sequence()

        if self.token.recognized_token != "μέχρι":
            self._syntax_error("'μέχρι'")
        self.nextToken()

        C_true, C_false = self.condition()

        self.icg.backpatch(C_false, S_quad)
        self.icg.backpatch(C_true, self.icg.nextquad())

    def for_stat(self):

        if self.token.recognized_token != "για":
            self._syntax_error("'για'")
        self.nextToken()

        if self.token.token_type != "IDENTIFIER":
            self._syntax_error("IDENTIFIER after 'για'")

        loop_var = self.token.recognized_token
        var_entity = self.st.lookup(loop_var)
        if var_entity is None:
            self._semantic_error(f"Loop variable '{loop_var}' undeclared")
        if not isinstance(var_entity, VariableEntity):
            self._semantic_error(f"Loop variable '{loop_var}' must be a variable")
        self.nextToken()

        if self.token.recognized_token != ":=":
            self._syntax_error("':=' in for loop")
        self.nextToken()

        start_val_place = self.expression()
        self.icg.genquad(":=", start_val_place, "_", loop_var)

        if self.token.recognized_token != "έως":
            self._syntax_error("'έως'")
        self.nextToken()

        end_val_place = self.expression()
        step_val_place = "1"

        if self.token.recognized_token == "με_βήμα":
            self.nextToken()
            step_val_place = self.expression()

        # The loop continues while var <= end for a non-negative step,
        # and while var >= end for a negative step
        loop_start_quad = self.icg.nextquad()

        positive_step_list = self.icg.makelist(self.icg.nextquad())
        self.icg.genquad(">=", step_val_place, "0", "_")
        negative_step_list = self.icg.makelist(self.icg.nextquad())
        self.icg.genquad("jump", "_", "_", "_")

        self.icg.backpatch(negative_step_list, self.icg.nextquad())
        cond_true_list = self.icg.makelist(self.icg.nextquad())
        self.icg.genquad(">=", loop_var, end_val_place, "_")
        cond_false_list = self.icg.makelist(self.icg.nextquad())
        self.icg.genquad("jump", "_", "_", "_")

        self.icg.backpatch(positive_step_list, self.icg.nextquad())
        cond_true_list = self.icg.mergelist(cond_true_list, self.icg.makelist(self.icg.nextquad()))
        self.icg.genquad("<=", loop_var, end_val_place, "_")
        cond_false_list = self.icg.mergelist(cond_false_list, self.icg.makelist(self.icg.nextquad()))
        self.icg.genquad("jump", "_", "_", "_")

        if self.token.recognized_token != "επανάλαβε":
            self._syntax_error("'επανάλαβε'")
        self.nextToken()

        self.icg.backpatch(cond_true_list, self.icg.nextquad())

        self.sequence()

        self.icg.genquad("+", loop_var, step_val_place, loop_var)
        self.icg.genquad("jump", "_", "_", loop_start_quad)

        self.icg.backpatch(cond_false_list, self.icg.nextquad())

        if self.token.recognized_token != "για_τέλος":
            self._syntax_error("'για_τέλος'")
        self.nextToken()

    def print_stat(self):

        if self.token.recognized_token != "γράψε":
            self._syntax_error("'γράψε'")
        self.nextToken()

        val_place = self.expression()

        self.icg.genquad("out", val_place, "_", "_")

    def input_stat(self):

        if self.token.recognized_token != "διάβασε":
            self._syntax_error("'διάβασε'")
        self.nextToken()

        if self.token.token_type != "IDENTIFIER":
            self._syntax_error("IDENTIFIER after 'διάβασε'")

        target_id = self.token.recognized_token
        target_entity = self.st.lookup(target_id)
        if target_entity is None:
             self._semantic_error(f"Input target '{target_id}' is undeclared")
        if not isinstance(target_entity, (VariableEntity, ParameterEntity)):
             self._semantic_error(f"Cannot read input into '{target_id}' (it's a {type(target_entity).__name__})")
        if isinstance(target_entity, ParameterEntity) and target_entity.mode == MODE_CV:
             self._semantic_error(f"Cannot read input into 'in' (CV) parameter '{target_id}'")

        self.icg.genquad("in", target_id, "_", "_")
        self.nextToken()

    def call_stat(self):

        if self.token.recognized_token != "εκτέλεσε":
            self._syntax_error("'εκτέλεσε'")
        self.nextToken()

        if self.token.token_type != "IDENTIFIER":
            self._syntax_error("Procedure/Function IDENTIFIER after 'εκτέλεσε'")

        call_name = self.token.recognized_token
        call_entity = self.st.lookup(call_name)
        if call_entity is None:
             self._semantic_error(f"Call to undeclared procedure/function '{call_name}'")
        if not isinstance(call_entity, (ProcedureEntity, FunctionEntity)):
             self._semantic_error(f"'{call_name}' is not a procedure or function, cannot call")
        self.nextToken()

        param_places_modes = self.idtail(call_entity, is_call=True)

        actual_param_count = len(param_places_modes) if param_places_modes else 0
        formal_param_count = len(call_entity.argument_list) if hasattr(call_entity, 'argument_list') else 0
        if actual_param_count != formal_param_count:
            self._semantic_error(f"Call to '{call_name}' expects {formal_param_count} arguments, got {actual_param_count}")

        if param_places_modes:
             self._check_param_modes(call_entity, param_places_modes)
             for place, mode in param_places_modes:
                 self.icg.genquad("par", place, mode, "_")

        # A function called as a statement still needs a place for its return value
        if not isinstance(call_entity, ProcedureEntity):
            return_temp = self.icg.newtemp(call_entity.type)
            self.icg.genquad("par", return_temp, MODE_RET, "_")

        self.icg.genquad("call", call_name, "_", "_")

    # Each actual parameter must use the same passing mode as the formal one
    def _check_param_modes(self, entity, params):
        for i in range(len(params)):
            place, mode = params[i]
            formal = entity.argument_list[i]
            if mode != formal.mode:
                if formal.mode == MODE_REF:
                    self._semantic_error(f"Parameter '{formal.name}' of '{entity.name}' is passed by reference, use '%{place}'")
                else:
                    self._semantic_error(f"Parameter '{formal.name}' of '{entity.name}' is passed by value, remove '%'")

    def idtail(self, entity, is_call=False):

        if self.token.recognized_token == "(":
            if not isinstance(entity, (FunctionEntity, ProcedureEntity)):
                 self._semantic_error(f"'{entity.name}' is not a function or procedure, cannot be called with '()'")

            param_info = self.actualpars()

            if is_call:
                if isinstance(entity, FunctionEntity) and entity.type != "void":
                     print(f"Warning (Line {self.token.line_number-1}): Function '{entity.name}' called as procedure (return value ignored).")
                return param_info
            else:
                if not isinstance(entity, FunctionEntity) or entity.type == "void":
                     self._semantic_error(f"'{entity.name}' is not a function returning a value, cannot be used in expression")

                actual_param_count = len(param_info) if param_info else 0
                formal_param_count = len(entity.argument_list)
                if actual_param_count != formal_param_count:
                    self._semantic_error(f"Function call '{entity.name}' expects {formal_param_count} arguments, got {actual_param_count}")

                if param_info:
                     self._check_param_modes(entity, param_info)
                     for place, mode in param_info:
                         self.icg.genquad("par", place, mode, "_")

                return_temp = self.icg.newtemp(entity.type)
                self.icg.genquad("par", return_temp, MODE_RET, "_")

                self.icg.genquad("call", entity.name, "_", "_")

                return return_temp
        else:
            if is_call:
                 if not isinstance(entity, ProcedureEntity):
                     self._semantic_error(f"'{entity.name}' requires '()' when called via 'εκτέλεσε' unless it's a procedure with no parameters.")
                 if len(entity.argument_list) > 0:
                     self._semantic_error(f"Procedure '{entity.name}' expects parameters, but called without '()'.")
                 return []
            else:
                 if not isinstance(entity, (VariableEntity, ParameterEntity, TemporaryEntity)):
                       self._semantic_error(f"'{entity.name}' is a function/procedure and cannot be used directly as a value here.")
                 return None

    def actualpars(self):

        if self.token.recognized_token != "(":
            self._syntax_error("'(' for actual parameters")
        self.nextToken()

        param_list = []
        if self.token.recognized_token != ")":
            param_list = self.actualparlist()
        if self.token.recognized_token != ")":
            self._syntax_error("')' after actual parameters")
        self.nextToken()
        return param_list

    def actualparlist(self):

        params = []
        place, mode = self.actualparitem()
        params.append((place, mode))
        while self.token.recognized_token == ",":
            self.nextToken()
            place, mode = self.actualparitem()
            params.append((place, mode))
        return params

    # "%x" passes x by reference; anything else is passed by value
    def actualparitem(self):

         if self.token.recognized_token == "%":
             mode = MODE_REF
             self.nextToken()

             if self.token.token_type != "IDENTIFIER":
                self._syntax_error("IDENTIFIER after '%'")

             ref_target_name = self.token.recognized_token
             ref_target_entity = self.st.lookup(ref_target_name)
             if ref_target_entity is None:
                 self._semantic_error(f"Passing undeclared identifier '{ref_target_name}' by reference (%)")
             if not isinstance(ref_target_entity, (VariableEntity, ParameterEntity)):
                  self._semantic_error(f"Cannot pass '{ref_target_name}' by reference (%), it must be a variable or parameter.")
             if isinstance(ref_target_entity, ParameterEntity) and ref_target_entity.mode == MODE_CV:
                  self._semantic_error(f"Cannot pass 'in' (CV) parameter '{ref_target_name}' by reference (%)")

             place = ref_target_name
             self.nextToken()
         else:
             mode = MODE_CV
             place = self.expression()
         return place, mode

    # Boolean expressions return (true_list, false_list) for backpatching
    def condition(self):

        Q1_true, Q1_false = self.boolterm()
        B_true = Q1_true
        B_false = Q1_false

        while self.token.recognized_token == "ή":
            self.nextToken()
            self.icg.backpatch(B_false, self.icg.nextquad())
            Q2_true, Q2_false = self.boolterm()
            B_true = self.icg.mergelist(B_true, Q2_true)
            B_false = Q2_false

        return B_true, B_false

    def boolterm(self):
        R1_true, R1_false = self.boolfactor()
        Q_true = R1_true
        Q_false = R1_false

        while self.token.recognized_token == "και":
            self.nextToken()
            self.icg.backpatch(Q_true, self.icg.nextquad())
            R2_true, R2_false = self.boolfactor()
            Q_false = self.icg.mergelist(Q_false, R2_false)
            Q_true = R2_true

        return Q_true, Q_false

    def boolfactor(self):

        if self.token.recognized_token == "όχι":
            self.nextToken()

            if self.token.recognized_token != "[":
                self._syntax_error("'[' after 'όχι'")
            self.nextToken()

            B_true, B_false = self.condition()

            if self.token.recognized_token != "]":
                self._syntax_error("']' after condition in 'όχι'")
            self.nextToken()

            return B_false, B_true
        elif self.token.recognized_token == "[":
            self.nextToken()

            B_true, B_false = self.condition()

            if self.token.recognized_token != "]":
                self._syntax_error("']' after condition")
            self.nextToken()

            return B_true, B_false
        else:
            E1_place = self.expression()

            if self.token.recognized_token in ("=", "<=", ">=", "<>", "<", ">"):
                op = self.token.recognized_token
                self.relational_oper()
                E2_place = self.expression()

                R_true = self.icg.makelist(self.icg.nextquad())
                self.icg.genquad(op, E1_place, E2_place, "_")
                R_false = self.icg.makelist(self.icg.nextquad())
                self.icg.genquad("jump", "_", "_", "_")

                return R_true, R_false
            else:
                 self._syntax_error("relational operator or end of boolean factor")

    def expression(self):

        sign = self.optional_sign()
        T1_place = self.term()

        if sign == '-':
             w = self.icg.newtemp()
             self.icg.genquad("-", "0", T1_place, w)
             T1_place = w

        E_place = T1_place

        while self.token.recognized_token in ("+", "-"):
            op = self.token.recognized_token

            self.add_oper()
            T2_place = self.term()

            w = self.icg.newtemp()
            self.icg.genquad(op, E_place, T2_place, w)
            E_place = w

        return E_place

    def term(self):

        F1_place = self.factor()
        T_place = F1_place

        while self.token.recognized_token in ("*", "/"):
            op = self.token.recognized_token

            self.mul_oper()
            F2_place = self.factor()

            w = self.icg.newtemp()
            self.icg.genquad(op, T_place, F2_place, w)
            T_place = w
        return T_place

    def factor(self):
        if self.token.token_type == "NUMBER":
            factor_place = self.token.recognized_token
            self.nextToken()

            return factor_place
        elif self.token.recognized_token == "(":
            self.nextToken()
            factor_place = self.expression()

            if self.token.recognized_token != ")":
                self._syntax_error("')'")
            self.nextToken()

            return factor_place
        elif self.token.token_type == "IDENTIFIER":
            id_name = self.token.recognized_token

            entity = self.st.lookup(id_name)
            if entity is None:
                 self._semantic_error(f"Undeclared identifier '{id_name}' used in expression")

            self.nextToken()
            func_result_temp = self.idtail(entity, is_call=False)

            if func_result_temp is not None:
                return func_result_temp
            else:
                if not isinstance(entity, (VariableEntity, ParameterEntity, TemporaryEntity)):
                      self._semantic_error(f"'{id_name}' is used as a value, but it's a {type(entity).__name__}")
                return id_name
        else:
            self._syntax_error("NUMBER, '(', or IDENTIFIER in factor")

    def relational_oper(self):
        if self.token.recognized_token in ("=", "<=", ">=", "<>", "<", ">"):
            self.nextToken()
        else: self._syntax_error("relational operator")

    def add_oper(self):
        if self.token.recognized_token in ("+", "-"):
            self.nextToken()
        else: self._syntax_error("add operator (+ or -)")

    def mul_oper(self):
        if self.token.recognized_token in ("*", "/"):
            self.nextToken()
        else: self._syntax_error("multiplication operator (* or /)")

    def optional_sign(self):
        if self.token.recognized_token in ("+", "-"):
            sign = self.token.recognized_token
            self.add_oper()
            return sign
        return None


if __name__ == '__main__':
    if len(sys.argv) > 1:
        filename = sys.argv[1]
        try:
            with open(filename, 'r', encoding='utf-8') as file:
                input_text = file.read()
        except FileNotFoundError:
            print(f"Error: file '{filename}' not found.")
            sys.exit(1)
    else:
        print("Usage: python compiler.py <filename>")
        sys.exit(1)
    try:
        tokens = lexicalAnalyzer(input_text)
        syntax_analyzer = SyntaxAnalyzer(tokens)
        syntax_analyzer.program(filename)
    except CompileError as e:
        print(e)
        sys.exit(1)