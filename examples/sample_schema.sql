-- SQL-of-Thought Sample Schema
-- E-commerce Database for Testing

-- Customers table
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    phone VARCHAR(20),
    address TEXT,
    city VARCHAR(50),
    country VARCHAR(50) DEFAULT 'USA',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Product categories
CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    parent_category_id INTEGER REFERENCES categories(category_id)
);

-- Products table
CREATE TABLE products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    sku VARCHAR(50) UNIQUE,
    category_id INTEGER REFERENCES categories(category_id),
    price DECIMAL(10, 2) NOT NULL,
    cost DECIMAL(10, 2),
    stock_quantity INTEGER DEFAULT 0,
    reorder_level INTEGER DEFAULT 10,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Orders table
CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER REFERENCES customers(customer_id),
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending',
    shipping_address TEXT,
    shipping_city VARCHAR(50),
    shipping_country VARCHAR(50),
    subtotal DECIMAL(10, 2),
    tax_amount DECIMAL(10, 2),
    shipping_cost DECIMAL(10, 2),
    total_amount DECIMAL(10, 2),
    notes TEXT
);

-- Order items (line items)
CREATE TABLE order_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER REFERENCES orders(order_id),
    product_id INTEGER REFERENCES products(product_id),
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL,
    discount DECIMAL(5, 2) DEFAULT 0,
    total DECIMAL(10, 2)
);

-- Product reviews
CREATE TABLE reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER REFERENCES products(product_id),
    customer_id INTEGER REFERENCES customers(customer_id),
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    title VARCHAR(200),
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_verified_purchase BOOLEAN DEFAULT FALSE
);

-- Inventory transactions
CREATE TABLE inventory_transactions (
    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER REFERENCES products(product_id),
    transaction_type VARCHAR(20) NOT NULL, -- 'purchase', 'sale', 'adjustment', 'return'
    quantity INTEGER NOT NULL,
    reference_id INTEGER, -- order_id or purchase_order_id
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Suppliers
CREATE TABLE suppliers (
    supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(200) NOT NULL,
    contact_name VARCHAR(100),
    email VARCHAR(100),
    phone VARCHAR(20),
    address TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

-- Product suppliers (many-to-many)
CREATE TABLE product_suppliers (
    product_id INTEGER REFERENCES products(product_id),
    supplier_id INTEGER REFERENCES suppliers(supplier_id),
    supplier_sku VARCHAR(50),
    cost DECIMAL(10, 2),
    lead_time_days INTEGER,
    PRIMARY KEY (product_id, supplier_id)
);

-- Sample data insertion
INSERT INTO categories (name, description) VALUES
    ('Electronics', 'Electronic devices and accessories'),
    ('Clothing', 'Apparel and fashion items'),
    ('Books', 'Physical and digital books'),
    ('Home & Garden', 'Home improvement and garden supplies');

INSERT INTO customers (first_name, last_name, email, city, country) VALUES
    ('John', 'Doe', 'john.doe@email.com', 'New York', 'USA'),
    ('Jane', 'Smith', 'jane.smith@email.com', 'Los Angeles', 'USA'),
    ('Bob', 'Johnson', 'bob.j@email.com', 'Chicago', 'USA'),
    ('Alice', 'Williams', 'alice.w@email.com', 'Houston', 'USA'),
    ('Charlie', 'Brown', 'charlie.b@email.com', 'Phoenix', 'USA');

INSERT INTO products (name, category_id, price, stock_quantity, sku) VALUES
    ('Smartphone X', 1, 999.99, 50, 'PHONE-001'),
    ('Laptop Pro', 1, 1499.99, 30, 'LAPTOP-001'),
    ('Wireless Earbuds', 1, 149.99, 100, 'AUDIO-001'),
    ('Cotton T-Shirt', 2, 29.99, 200, 'SHIRT-001'),
    ('Denim Jeans', 2, 79.99, 150, 'JEANS-001'),
    ('Programming Guide', 3, 49.99, 75, 'BOOK-001'),
    ('Garden Tools Set', 4, 89.99, 40, 'GARDEN-001');

INSERT INTO orders (customer_id, status, total_amount) VALUES
    (1, 'completed', 1149.98),
    (2, 'completed', 79.99),
    (3, 'pending', 999.99),
    (1, 'completed', 149.99),
    (4, 'shipped', 1579.98);

INSERT INTO order_items (order_id, product_id, quantity, unit_price, total) VALUES
    (1, 1, 1, 999.99, 999.99),
    (1, 3, 1, 149.99, 149.99),
    (2, 5, 1, 79.99, 79.99),
    (3, 1, 1, 999.99, 999.99),
    (4, 3, 1, 149.99, 149.99),
    (5, 2, 1, 1499.99, 1499.99),
    (5, 5, 1, 79.99, 79.99);

INSERT INTO reviews (product_id, customer_id, rating, title, content, is_verified_purchase) VALUES
    (1, 1, 5, 'Amazing phone!', 'Best smartphone I have ever used.', TRUE),
    (1, 2, 4, 'Great but pricey', 'Excellent features but expensive.', TRUE),
    (3, 1, 5, 'Perfect sound', 'Crystal clear audio quality.', TRUE),
    (2, 4, 5, 'Powerful laptop', 'Great for programming and design work.', TRUE);
