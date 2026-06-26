import sqlite3


def init_db():
    conn = sqlite3.connect("demo.db")
    cur = conn.cursor()

    cur.executescript("""
        DROP TABLE IF EXISTS enrollments;
        DROP TABLE IF EXISTS students;
        DROP TABLE IF EXISTS courses;
        DROP TABLE IF EXISTS employees;
        DROP TABLE IF EXISTS departments;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS orders;

        CREATE TABLE students (
            id      INTEGER PRIMARY KEY,
            name    TEXT,
            age     INTEGER,
            grade   TEXT,
            city    TEXT
        );

        CREATE TABLE courses (
            id      INTEGER PRIMARY KEY,
            name    TEXT,
            credits INTEGER,
            teacher TEXT
        );

        CREATE TABLE enrollments (
            id         INTEGER PRIMARY KEY,
            student_id INTEGER,
            course_id  INTEGER,
            score      INTEGER,
            FOREIGN KEY(student_id) REFERENCES students(id),
            FOREIGN KEY(course_id)  REFERENCES courses(id)
        );

        CREATE TABLE employees (
            id         INTEGER PRIMARY KEY,
            name       TEXT,
            age        INTEGER,
            salary     REAL,
            department TEXT
        );

        CREATE TABLE departments (
            id     INTEGER PRIMARY KEY,
            name   TEXT,
            budget REAL,
            head   TEXT
        );

        CREATE TABLE products (
            id       INTEGER PRIMARY KEY,
            name     TEXT,
            category TEXT,
            price    REAL,
            stock    INTEGER
        );

        CREATE TABLE orders (
            id         INTEGER PRIMARY KEY,
            product_id INTEGER,
            quantity   INTEGER,
            total      REAL,
            status     TEXT,
            order_date TEXT,
            FOREIGN KEY(product_id) REFERENCES products(id)
        );
    """)

    cur.executemany("INSERT INTO students VALUES (?,?,?,?,?)", [
        (1, "Alice",   20, "A", "Mumbai"),
        (2, "Bob",     22, "B", "Pune"),
        (3, "Charlie", 21, "A", "Mumbai"),
        (4, "Diana",   23, "C", "Delhi"),
        (5, "Eve",     20, "B", "Pune"),
        (6, "Frank",   24, "A", "Chennai"),
        (7, "Grace",   21, "B", "Mumbai"),
    ])

    cur.executemany("INSERT INTO courses VALUES (?,?,?,?)", [
        (1, "Mathematics",      4, "Dr. Sharma"),
        (2, "Physics",          3, "Dr. Mehta"),
        (3, "Computer Science", 4, "Dr. Joshi"),
        (4, "English",          2, "Dr. Rao"),
        (5, "Data Science",     4, "Dr. Patel"),
    ])

    cur.executemany("INSERT INTO enrollments VALUES (?,?,?,?)", [
        (1, 1, 1, 85), (2, 1, 3, 92), (3, 2, 1, 76),
        (4, 2, 2, 88), (5, 3, 3, 95), (6, 4, 4, 70),
        (7, 5, 1, 80), (8, 5, 3, 89), (9, 6, 5, 94),
        (10, 7, 2, 78), (11, 1, 5, 91), (12, 3, 1, 87),
    ])

    cur.executemany("INSERT INTO employees VALUES (?,?,?,?,?)", [
        (1, "Rahul",  30, 50000, "Engineering"),
        (2, "Priya",  28, 60000, "Engineering"),
        (3, "Amit",   35, 80000, "Management"),
        (4, "Sneha",  26, 45000, "Marketing"),
        (5, "Raj",    40, 90000, "Management"),
        (6, "Kavya",  29, 55000, "Engineering"),
        (7, "Vikram", 33, 70000, "Marketing"),
    ])

    cur.executemany("INSERT INTO departments VALUES (?,?,?,?)", [
        (1, "Engineering", 500000, "Rahul"),
        (2, "Management",  800000, "Amit"),
        (3, "Marketing",   300000, "Sneha"),
    ])

    cur.executemany("INSERT INTO products VALUES (?,?,?,?,?)", [
        (1, "Laptop",     "Electronics", 75000, 10),
        (2, "Phone",      "Electronics", 25000, 25),
        (3, "Desk Chair", "Furniture",    8000, 15),
        (4, "Notebook",   "Stationery",    150, 100),
        (5, "Headphones", "Electronics",  5000, 30),
    ])

    cur.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?)", [
        (1, 1, 2, 150000, "Delivered",  "2024-01-10"),
        (2, 2, 5, 125000, "Delivered",  "2024-01-15"),
        (3, 3, 1,   8000, "Processing", "2024-02-01"),
        (4, 5, 3,  15000, "Delivered",  "2024-02-10"),
        (5, 2, 2,  50000, "Shipped",    "2024-03-01"),
        (6, 1, 1,  75000, "Processing", "2024-03-05"),
        (7, 4, 20,  3000, "Delivered",  "2024-03-10"),
    ])

    conn.commit()
    conn.close()
    print("✅ Demo database initialised with 7 tables!")


if __name__ == "__main__":
    init_db()
