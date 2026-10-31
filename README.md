# greek++ Compiler

A compiler for **greek++**, a small educational programming language with **Greek keywords**, defined for the course. It translates greek++ programs into **RISC-V assembly**, which can be run in the [RARS](https://github.com/TheThirdOne/rars) simulator.

Written in Python for the **Compilers** course at the Department of Computer Science & Engineering, University of Ioannina (2025).

## Example

```
πρόγραμμα παράδειγμα
δήλωση n

συνάρτηση παραγοντικό(κ)
διαπροσωπεία
είσοδος κ
αρχή_συνάρτησης
    εάν κ <= 1 τότε
        παραγοντικό := 1
    αλλιώς
        παραγοντικό := κ * παραγοντικό(κ - 1)
    εάν_τέλος
τέλος_συνάρτησης

αρχή_προγράμματος
    διάβασε n;
    γράψε παραγοντικό(n)
τέλος_προγράμματος
```

## How the compiler works
The compiler runs in a single pass over the source code:

1. **Lexical analysis:** splits the source into tokens (keywords, identifiers, numbers, operators). Supports Greek and Latin identifiers and nested `{ }` comments.
2. **Syntax analysis:** a recursive-descent parser, with one method per grammar rule, that also performs **semantic checks** (undeclared names, wrong number of arguments, wrong parameter passing mode, redeclarations, modifying the variable of a `για` loop inside the loop).
3. **Symbol table:** keeps nested scopes, the memory offset of every variable and the information about each function/procedure. Written to `<program>.sym`.
4. **Intermediate code:** generated as **quadruples** during parsing, using backpatching for conditions and loops. Written to `<program>.int`.
5. **Final code:** translates the quadruples into **RISC-V assembly**, with activation records on the stack, access links for nested subprograms, and parameters passed by value or by reference. Written to `<program>.asm`.

## The language

| greek++ | Meaning |
|---|---|
| `πρόγραμμα name` | Program header |
| `δήλωση a, b` | Variable declaration (all variables are integers) |
| `αρχή_προγράμματος ... τέλος_προγράμματος` | Main program |
| `x := expr` | Assignment |
| `εάν cond τότε ... αλλιώς ... εάν_τέλος` | If / else |
| `όσο cond επανάλαβε ... όσο_τέλος` | While loop |
| `επανάλαβε ... μέχρι cond` | Repeat until |
| `για i := a έως b με_βήμα s επανάλαβε ... για_τέλος` | For loop; `με_βήμα` is optional (default 1) and the step can be negative. `i` cannot be modified inside the loop |
| `διάβασε x` / `γράψε expr` | Read an integer / print an integer |
| `+ - * /` and `= <> < > <= >=` | Arithmetic (integer division) and relational operators |
| `και`, `ή`, `όχι [ ... ]` | Logical and, or, not; `[ ]` groups conditions |
| `συνάρτηση f(...) ... αρχή_συνάρτησης ... τέλος_συνάρτησης` | Function (returns a value with `f := expr`) |
| `διαδικασία p(...) ... αρχή_διαδικασίας ... τέλος_διαδικασίας` | Procedure |
| `διαπροσωπεία`, `είσοδος x`, `έξοδος y` | Subprogram interface: `είσοδος` parameters are passed by value, `έξοδος` parameters by reference |
| `εκτέλεσε p(a, %b)` | Call a procedure; `%b` passes `b` by reference |
| `{ ... }` | Comment |

Statements are separated by `;`. Identifiers consist of Greek or Latin letters, digits and `_`, start with a letter and have up to 30 characters. Functions and procedures can be nested and recursive, and a nested subprogram can access the variables of the subprograms that enclose it.

## Requirements
- Python 3.8+
- To run the generated assembly: Java and the [RARS](https://github.com/TheThirdOne/rars/releases) simulator (`rars1_6.jar`)

## Usage

Compile a program:
```bash
python compiler.py tests/gtest1.gr
```
This creates `gtest1.int` (intermediate code), `gtest1.sym` (symbol table) and `gtest1.asm` (RISC-V assembly) next to the source file.

Run the generated assembly in RARS:
```bash
java -jar rars1_6.jar nc tests/gtest1.asm
```
You can also open the `.asm` file in the RARS graphical interface, assemble it and run it.

If the program has an error, the compiler reports it with its line number, for example:
```
Semantic error (line 3): Undeclared identifier 'x' used in expression
```

## Test programs
The `tests/` folder contains example greek++ programs, including the test programs provided by the course (`gtest1`–`gtest4`):

| Program | What it tests | Input | Output |
|---|---|---|---|
| `gtest1.gr` | Fibonacci and factorial with `όσο` and `επανάλαβε` | – | `0 1 1 2 3 5 8 13 21 34 55 1 1 2 6 24 120 720` |
| `gtest2.gr` | Loops, signs, if/else | – | `10 0 -2 1` |
| `gtest3.gr` | Income tax with nested `εάν` | `25000` | `1500` |
| `gtest4.gr` | Loan approval with complex conditions | `30 700 25000` | `1` |
| `test5final.gr` | Function with a parameter passed by reference | – | `2 2` |
| `testprogram.gr` | The example program of the language specification | `-200` | `2 4 6 8` |

Each number is printed on its own line; inputs are given one per line.

## Authors
- **Athanasios Tonios** — [GitHub](https://github.com/athanasios-tonios)

