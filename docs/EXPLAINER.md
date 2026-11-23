# How it works, in plain words

This is the companion to the report: the same ideas without the formal wording, followed by the questions you are most likely to be asked when presenting. The measured numbers are in the report's tables, so they are not repeated here.

## The problem in one paragraph

The program multiplies two matrices and takes three determinants, and every number in those matrices is an element of a finite field with 1,331 elements. The original library stores an element as a small polynomial and does real polynomial arithmetic every time two elements are added or multiplied. A 4000 × 4000 run asks for about 320 billion of those operations. But there are only 1,331 different elements, so there are only 1,331 × 1,331 = 1,771,561 different multiplications that can ever be asked for. The program keeps redoing the same sums.

## Part 1: the cache

### The idea

Do each sum once, write the answer down, and look it up after that.

- An element is no longer stored as a polynomial. It is stored as a number from 0 to 1330, its **index**. The index is the element's three coefficients read as a base-11 number: `c0 + 11·c1 + 121·c2`. That is the same numbering the original library already uses in `from_index`.
- Each operation has a **table**. For multiplication the table has one slot for every pair `(a, b)`, at position `a × 1331 + b`.
- A slot starts out empty (it holds 0).

### One multiplication, step by step

1. Look at slot `a × 1331 + b` in the products table.
2. If it is not empty, that is a **cache hit**. Return what is in it. Done.
3. If it is empty, that is a **cache miss**. Take the two original polynomial elements, multiply them with the original library's code, turn the answer back into an index, write it into the slot, and return it.

Addition works the same way with its own table. Negation and reciprocal have smaller tables with one slot per element.

A slot is filled once and never changes, so the original code runs at most about 3.5 million times in total, no matter how big the matrices are. Everything after that is a table read.

### Why it is a "drop-in"

The assignment asks that nothing else has to change. So the cached library keeps:

- the same header file names (`algebra/finite_fields/finite_field.hpp` and the rest),
- the same class names (`algebra::FiniteField`, `algebra::FiniteFieldElement`),
- the same functions on those classes,
- the same CMake target name (`algebra::finite_fields`).

The original class is still there. Its file was renamed to `uncached_finite_field.hpp` and one line was changed so that it lives in the namespace `algebra::uncached`. The new class calls it on every cache miss. The program switches by changing two lines in `cmake/Dependencies.cmake`, the repository address and the commit.

### How we know the answers are the same

The field is small enough to check everything.

- The professor's own test file runs unchanged against the cached class and passes.
- A new test compares cached and original for every element and for all 1,771,561 pairs, for add and for multiply. It goes through the pairs twice, because the first time through is all misses and the second time is all hits, and both have to be right.
- The assignment program prints the same determinants with either library.

### What it costs

- The tables take about 7 MB, whatever the matrix size. For tiny matrices that makes the cached program use more memory than the original.
- The first use of each pair is still slow, and storing the result adds a little on top. A 100 × 100 run is mostly first uses, so it gains almost nothing. The gain appears as the matrices grow and the same pairs come back.

## Part 2: the MPI determinant

### What a determinant needs

The program finds a determinant by Gaussian elimination. Working through the columns from left to right, for column `k` it:

1. finds a nonzero entry in column `k`, at row `k` or below (the **pivot**), and swaps that row up to row `k`;
2. divides everything below the pivot in that column by the pivot (the **multipliers**);
3. for every row below, subtracts multiplier × row `k`, which turns the rest of column `k` into zeros.

The determinant is the product of all the pivots, with the sign flipped once for every swap. If some column has no nonzero entry to use as a pivot, the determinant is zero. This is the same thing as a PLU decomposition: P records the swaps, L holds the multipliers, U is what is left.

### The key decision: split the matrix by columns

Step `k` needs the pivot and the multipliers. Both come from column `k` only.

So each process owns whole columns. Whoever owns column `k` already has everything needed to pick the pivot and compute the multipliers. It does not have to ask anyone. It then sends one message to everybody: "the pivot was in row r, and here are the multipliers." Every process uses that message to update the columns it owns.

If the matrix were split by rows instead, column `k` would be scattered over all the processes. Finding a nonzero pivot would mean asking everyone at every step, and a swap could mean two processes mailing rows to each other.

### Panels

One message per column is a lot of small messages. So columns are grouped into **panels** of `b` columns (8 by default). The owner works through the `b` columns of its panel, then sends one message for the whole panel. Panels are dealt out like cards: panel 0 to process 0, panel 1 to process 1, and so on, round and round, so that every process still has work near the end.

### What is actually sent

- Once at the start: process 0 sends each process its columns.
- Then one broadcast per panel: a "determinant is zero" flag, the pivot rows, and the multipliers.

Because a cached element is just a 2-byte number, a column goes over the network as raw bytes. With the original library each element owns its own piece of heap memory and could not be sent that way.

### Why MPI loses on small matrices

Sending a message has a fixed cost that does not depend on how much arithmetic there is. A small determinant is a few microseconds of arithmetic, which is less than the cost of the messages. The arithmetic grows with N³, the number of messages only with N. Somewhere the arithmetic takes over, and that size is the break-even point the assignment asks for.

## Questions you may be asked

**Why did you cache the finite field class and not something else?**
The profile shows where the instructions are: most are lines of the polynomial, ring and group libraries underneath the finite field class, and most of the rest are `std::vector` and memory allocator code, which is how the polynomials are stored. The lines of the matrix library and of `main.cpp` are a fraction of a percent. In the product and the elimination, all of that work is reached through four functions of that one class: add, negate, multiply, reciprocal. Caching there means the matrix library, the program, and the polynomial, ring and group libraries underneath all stay as they are.

**The assignment suggests `std::unordered_map`. Why didn't you use it?**
We measured it. A hash map lookup has to compute a hash, read a bucket, and then follow a pointer to a node on the heap, each read waiting for the one before, so each lookup waits on memory. In the matrix product, where each addition needs the previous result first, those waits line up one after another. Our elements are already numbers from 0 to 1330, so the pair `(a, b)` is a perfect array position and no hashing is needed.

**What exactly happens on a cache miss?**
The two original polynomial elements are looked up in a list, the original library's function is called on them, the result is converted to its index, and the index is stored in the slot.

**How do you turn a polynomial into an index and back?**
Polynomial to index: read the three coefficients as a base-11 number. Index to polynomial: a list of all 1,331 original elements is built once, and the index is the position in that list.

**Is the modulus the same?**
Yes. The cached class does not pick a modulus. It asks the original class for it, so both use `x³ + x + 4`.

**How do you know it is correct?**
Every element and every pair of elements is compared with the original in the unit tests, on both the miss and the hit, plus the professor's unchanged tests and the determinants from the real program.

**Why is there almost no speedup for small matrices?**
The first use of each pair still runs the original arithmetic, and then has to store the result. A small run is mostly first uses, so there is little left to save.

**Why does the cached version sometimes use more memory?**
The tables are a fixed 7 MB. For the smallest matrices that is more than the two-byte entries save, so the cached program uses more memory in total. In our runs it used less from 200 × 200 upward.

**Is it safe with threads?**
Yes. Each slot is an atomic value. If two threads miss on the same slot they both compute the same answer and both store it, so no lock is needed.

**What if the field were much bigger?**
The pair tables grow with the square of the field size. Above 4,096 elements the class does not build tables. It stores the original element and passes every call through.

**Why is the matrix product now the slowest part?**
In the product each entry is built as a running sum, so each addition has to wait for the one before. In the elimination the additions are independent and the processor can overlap them.

**Why columns and not rows for MPI?**
The pivot and the multipliers for a step both live in one column. With columns, one process has them and nobody has to be asked.

**What is the panel width for?**
It sets how many columns are handled per message. Wider panels mean fewer, bigger messages, but the other processes wait longer while one process prepares a panel.

**How is the sign of the determinant handled?**
Every broadcast includes which row was swapped in at each step. A swap with a different row flips the sign once.

**What happens with a singular matrix?**
The owner of the panel finds a column with nothing usable as a pivot, sets a flag in its broadcast, and every process stops with a determinant of zero.

**Is the MPI program with one process the same as the sequential program?**
Not the same code. It sends nothing, but it stores the matrix by columns and updates one column at a time, where the sequential program works row by row. The inner loop does the same three table lookups per entry in both. The report gives the measured ratio between the two, and it measures the gain from adding processes against the one-process MPI run for that reason.

**How do you know the MPI answer is right?**
Every run also computes the determinant sequentially on the same matrix and compares. The test script does this for many sizes, process counts, panel widths and special matrices, and checks three sizes against the original program's printed determinants.

**How was MPI timed against the sequential program?**
In the same job, on the same matrix, one right after the other. Process 0 runs the sequential elimination while the other processes sleep, and then all of them run the MPI version. The two take turns going first. That matters for small matrices: whichever runs second finds the table entries it needs already in the processor's cache, because the first one just used them.

**Does every process have its own cache?**
Yes. Processes do not share memory, so each one has its own tables and fills them before the timing starts.
