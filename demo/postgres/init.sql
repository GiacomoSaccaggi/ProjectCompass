-- Demo Store: products, customers, orders

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    price NUMERIC(10,2) NOT NULL,
    stock INT NOT NULL DEFAULT 0
);

CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    country VARCHAR(60) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INT REFERENCES customers(id),
    product_id INT REFERENCES products(id),
    quantity INT NOT NULL,
    total NUMERIC(10,2) NOT NULL,
    order_date DATE NOT NULL
);

INSERT INTO products (name, category, price, stock) VALUES
('Wireless Mouse', 'Electronics', 29.99, 150),
('Mechanical Keyboard', 'Electronics', 89.99, 75),
('USB-C Hub', 'Electronics', 49.99, 200),
('Monitor Stand', 'Accessories', 34.99, 120),
('Webcam HD', 'Electronics', 59.99, 90),
('Desk Lamp', 'Accessories', 24.99, 300),
('Laptop Sleeve', 'Accessories', 19.99, 250),
('External SSD 1TB', 'Storage', 109.99, 60),
('Bluetooth Speaker', 'Audio', 39.99, 180),
('Noise-Cancelling Headphones', 'Audio', 199.99, 45),
('Ergonomic Chair', 'Furniture', 349.99, 30),
('Standing Desk', 'Furniture', 499.99, 20),
('Cable Management Kit', 'Accessories', 14.99, 400),
('Portable Charger', 'Electronics', 29.99, 160),
('Screen Protector', 'Accessories', 9.99, 500);

INSERT INTO customers (name, email, country) VALUES
('Alice Martin', 'alice.martin@example.com', 'France'),
('Bob Smith', 'bob.smith@example.com', 'United States'),
('Carla Rossi', 'carla.rossi@example.com', 'Italy'),
('David Chen', 'david.chen@example.com', 'China'),
('Elena Petrova', 'elena.petrova@example.com', 'Russia'),
('Frank Mueller', 'frank.mueller@example.com', 'Germany'),
('Giulia Bianchi', 'giulia.bianchi@example.com', 'Italy'),
('Hiroshi Tanaka', 'hiroshi.tanaka@example.com', 'Japan'),
('Isabel Garcia', 'isabel.garcia@example.com', 'Spain'),
('Jan Novak', 'jan.novak@example.com', 'Czech Republic'),
('Kim Soo-yeon', 'kim.sooyeon@example.com', 'South Korea'),
('Luca Ferrari', 'luca.ferrari@example.com', 'Italy');

INSERT INTO orders (customer_id, product_id, quantity, total, order_date) VALUES
(1, 1, 2, 59.98, '2025-01-10'),
(1, 6, 1, 24.99, '2025-01-10'),
(2, 2, 1, 89.99, '2025-01-15'),
(3, 10, 1, 199.99, '2025-02-01'),
(3, 9, 2, 79.98, '2025-02-01'),
(4, 8, 1, 109.99, '2025-02-14'),
(5, 11, 1, 349.99, '2025-02-20'),
(6, 3, 3, 149.97, '2025-03-01'),
(7, 5, 1, 59.99, '2025-03-05'),
(7, 4, 1, 34.99, '2025-03-05'),
(8, 12, 1, 499.99, '2025-03-10'),
(9, 7, 2, 39.98, '2025-03-15'),
(10, 14, 1, 29.99, '2025-03-20'),
(11, 13, 5, 74.95, '2025-04-01'),
(12, 1, 1, 29.99, '2025-04-05'),
(1, 8, 1, 109.99, '2025-04-10'),
(2, 10, 1, 199.99, '2025-04-15'),
(3, 3, 1, 49.99, '2025-04-20'),
(4, 15, 3, 29.97, '2025-05-01'),
(5, 2, 1, 89.99, '2025-05-05'),
(6, 9, 1, 39.99, '2025-05-10'),
(7, 6, 2, 49.98, '2025-05-15'),
(8, 14, 2, 59.98, '2025-05-20'),
(9, 11, 1, 349.99, '2025-06-01'),
(10, 5, 1, 59.99, '2025-06-10'),
(11, 4, 3, 104.97, '2025-06-15'),
(12, 12, 1, 499.99, '2025-06-20'),
(1, 13, 2, 29.98, '2025-07-01'),
(3, 7, 1, 19.99, '2025-07-10'),
(5, 1, 1, 29.99, '2025-07-15');
