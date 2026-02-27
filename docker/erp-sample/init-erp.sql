-- =============================================================================
-- ERP Sample Database - Enterprise Resource Management
-- =============================================================================
-- Idempotent script: safe to run multiple times.
-- Populates a realistic ERP dataset for agent-based deep research testing.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Schema: tables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    budget NUMERIC(12,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS employees (
    id SERIAL PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    department_id INTEGER REFERENCES departments(id),
    hire_date DATE NOT NULL,
    salary NUMERIC(10,2) NOT NULL,
    manager_id INTEGER REFERENCES employees(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS product_categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    category_id INTEGER REFERENCES product_categories(id),
    sku VARCHAR(50) NOT NULL UNIQUE,
    unit_price NUMERIC(10,2) NOT NULL,
    cost_price NUMERIC(10,2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    company_name VARCHAR(200) NOT NULL,
    contact_name VARCHAR(100),
    email VARCHAR(150),
    phone VARCHAR(30),
    city VARCHAR(100),
    country VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    order_date DATE NOT NULL,
    ship_date DATE,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    total_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(10,2) NOT NULL,
    discount NUMERIC(5,2) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS inventory (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id),
    warehouse_location VARCHAR(50) NOT NULL,
    quantity_on_hand INTEGER NOT NULL DEFAULT 0,
    reorder_level INTEGER NOT NULL DEFAULT 10,
    last_restock_date DATE
);

CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    department_id INTEGER REFERENCES departments(id),
    lead_employee_id INTEGER REFERENCES employees(id),
    start_date DATE NOT NULL,
    end_date DATE,
    budget NUMERIC(12,2) NOT NULL DEFAULT 0,
    status VARCHAR(30) NOT NULL DEFAULT 'planning'
);

CREATE TABLE IF NOT EXISTS project_assignments (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    role VARCHAR(100) NOT NULL,
    hours_allocated INTEGER NOT NULL DEFAULT 0,
    UNIQUE(project_id, employee_id)
);

-- ---------------------------------------------------------------------------
-- Indexes for join performance
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_employees_department ON employees(department_id);
CREATE INDEX IF NOT EXISTS idx_employees_manager ON employees(manager_id);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_employee ON orders(employee_id);
CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(order_date);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product ON order_items(product_id);
CREATE INDEX IF NOT EXISTS idx_inventory_product ON inventory(product_id);
CREATE INDEX IF NOT EXISTS idx_projects_department ON projects(department_id);
CREATE INDEX IF NOT EXISTS idx_project_assignments_project ON project_assignments(project_id);
CREATE INDEX IF NOT EXISTS idx_project_assignments_employee ON project_assignments(employee_id);

-- ---------------------------------------------------------------------------
-- Seed Data
-- ---------------------------------------------------------------------------

-- Departments (8)
INSERT INTO departments (id, name, budget) VALUES
    (1, 'Engineering',    2500000.00),
    (2, 'Sales',          1800000.00),
    (3, 'Marketing',      1200000.00),
    (4, 'Human Resources',  800000.00),
    (5, 'Finance',         900000.00),
    (6, 'Operations',     1500000.00),
    (7, 'Customer Support', 700000.00),
    (8, 'Research & Development', 2000000.00)
ON CONFLICT (id) DO NOTHING;
SELECT setval('departments_id_seq', 8, true);

-- Employees (50) - managers first, then staff
INSERT INTO employees (id, first_name, last_name, email, department_id, hire_date, salary, manager_id) VALUES
    -- Department heads (no manager)
    (1,  'Alice',   'Chen',      'alice.chen@company.com',       1, '2019-03-15', 185000.00, NULL),
    (2,  'Bob',     'Martinez',  'bob.martinez@company.com',     2, '2018-07-01', 175000.00, NULL),
    (3,  'Carol',   'Johnson',   'carol.johnson@company.com',    3, '2019-01-10', 160000.00, NULL),
    (4,  'David',   'Kim',       'david.kim@company.com',        4, '2017-11-20', 155000.00, NULL),
    (5,  'Eva',     'Patel',     'eva.patel@company.com',        5, '2018-04-05', 170000.00, NULL),
    (6,  'Frank',   'Wilson',    'frank.wilson@company.com',     6, '2019-06-15', 165000.00, NULL),
    (7,  'Grace',   'Lee',       'grace.lee@company.com',        7, '2020-02-01', 145000.00, NULL),
    (8,  'Henry',   'Taylor',    'henry.taylor@company.com',     8, '2018-09-10', 190000.00, NULL),
    -- Engineering team
    (9,  'Ivan',    'Novak',     'ivan.novak@company.com',       1, '2020-01-15', 135000.00, 1),
    (10, 'Julia',   'Santos',    'julia.santos@company.com',     1, '2020-06-01', 130000.00, 1),
    (11, 'Kevin',   'Brown',     'kevin.brown@company.com',      1, '2021-03-20', 120000.00, 9),
    (12, 'Lisa',    'Wang',      'lisa.wang@company.com',        1, '2021-08-15', 125000.00, 9),
    (13, 'Mike',    'Garcia',    'mike.garcia@company.com',      1, '2022-01-10', 115000.00, 10),
    (14, 'Nina',    'Andersson', 'nina.andersson@company.com',   1, '2022-05-01', 118000.00, 10),
    -- Sales team
    (15, 'Oscar',   'Dubois',    'oscar.dubois@company.com',     2, '2019-09-01', 120000.00, 2),
    (16, 'Priya',   'Sharma',    'priya.sharma@company.com',     2, '2020-03-15', 115000.00, 2),
    (17, 'Quinn',   'O''Brien',  'quinn.obrien@company.com',     2, '2020-11-01', 110000.00, 15),
    (18, 'Rita',    'Muller',    'rita.muller@company.com',       2, '2021-02-20', 105000.00, 15),
    (19, 'Sam',     'Tanaka',    'sam.tanaka@company.com',       2, '2021-07-10', 108000.00, 16),
    (20, 'Tara',    'Ivanov',    'tara.ivanov@company.com',      2, '2022-04-01', 100000.00, 16),
    -- Marketing team
    (21, 'Uma',     'Fischer',   'uma.fischer@company.com',      3, '2020-05-01', 105000.00, 3),
    (22, 'Victor',  'Costa',     'victor.costa@company.com',     3, '2021-01-15', 98000.00,  3),
    (23, 'Wendy',   'Park',      'wendy.park@company.com',       3, '2021-09-01', 95000.00,  21),
    (24, 'Xavier',  'Ali',       'xavier.ali@company.com',       3, '2022-02-10', 92000.00,  21),
    -- HR team
    (25, 'Yuki',    'Sato',      'yuki.sato@company.com',        4, '2019-10-01', 95000.00,  4),
    (26, 'Zoe',     'Adams',     'zoe.adams@company.com',        4, '2021-04-15', 88000.00,  4),
    (27, 'Aaron',   'Lim',       'aaron.lim@company.com',        4, '2022-06-01', 85000.00,  25),
    -- Finance team
    (28, 'Bella',   'Rossi',     'bella.rossi@company.com',      5, '2019-08-01', 120000.00, 5),
    (29, 'Carlos',  'Reyes',     'carlos.reyes@company.com',     5, '2020-12-01', 110000.00, 5),
    (30, 'Diana',   'Popov',     'diana.popov@company.com',      5, '2021-06-15', 105000.00, 28),
    -- Operations team
    (31, 'Ethan',   'Moreau',    'ethan.moreau@company.com',     6, '2019-12-01', 110000.00, 6),
    (32, 'Fiona',   'Berg',      'fiona.berg@company.com',       6, '2020-07-15', 105000.00, 6),
    (33, 'George',  'Nakamura',  'george.nakamura@company.com',  6, '2021-05-01', 98000.00,  31),
    (34, 'Hannah',  'Silva',     'hannah.silva@company.com',     6, '2022-01-15', 95000.00,  31),
    -- Customer Support team
    (35, 'Ian',     'Kowalski',  'ian.kowalski@company.com',     7, '2020-04-01', 90000.00,  7),
    (36, 'Jade',    'Nguyen',    'jade.nguyen@company.com',      7, '2021-03-01', 85000.00,  7),
    (37, 'Karl',    'Eriksson',  'karl.eriksson@company.com',    7, '2021-10-15', 82000.00,  35),
    (38, 'Luna',    'Gonzalez',  'luna.gonzalez@company.com',    7, '2022-03-01', 80000.00,  35),
    -- R&D team
    (39, 'Marco',   'Bianchi',   'marco.bianchi@company.com',    8, '2019-05-01', 145000.00, 8),
    (40, 'Nadia',   'Petrov',    'nadia.petrov@company.com',     8, '2020-02-15', 140000.00, 8),
    (41, 'Oliver',  'Schmidt',   'oliver.schmidt@company.com',   8, '2020-10-01', 130000.00, 39),
    (42, 'Petra',   'Johansson', 'petra.johansson@company.com',  8, '2021-04-15', 128000.00, 39),
    (43, 'Raj',     'Gupta',     'raj.gupta@company.com',        8, '2021-11-01', 125000.00, 40),
    (44, 'Sofia',   'Lopez',     'sofia.lopez@company.com',      8, '2022-05-15', 122000.00, 40),
    -- Additional staff
    (45, 'Tom',     'Wright',    'tom.wright@company.com',       1, '2022-09-01', 112000.00, 9),
    (46, 'Ursula',  'Hoffman',   'ursula.hoffman@company.com',   2, '2022-08-15', 98000.00,  15),
    (47, 'Vincent', 'Cheung',    'vincent.cheung@company.com',   6, '2022-10-01', 92000.00,  32),
    (48, 'Wendy',   'Murphy',    'wendy.murphy@company.com',     3, '2023-01-15', 90000.00,  22),
    (49, 'Xander',  'Jensen',    'xander.jensen@company.com',    1, '2023-03-01', 110000.00, 10),
    (50, 'Yasmin',  'Okafor',    'yasmin.okafor@company.com',    2, '2023-02-01', 95000.00,  16)
ON CONFLICT (id) DO NOTHING;
SELECT setval('employees_id_seq', 50, true);

-- Product Categories (10)
INSERT INTO product_categories (id, name, description) VALUES
    (1,  'Electronics',        'Consumer and business electronics'),
    (2,  'Office Supplies',    'Paper, pens, organizational items'),
    (3,  'Furniture',          'Office and workspace furniture'),
    (4,  'Software Licenses',  'Enterprise and productivity software'),
    (5,  'Networking',         'Network equipment and cables'),
    (6,  'Storage',            'Hard drives, SSDs, cloud storage'),
    (7,  'Peripherals',        'Keyboards, mice, monitors, webcams'),
    (8,  'Security',           'Cybersecurity and physical security'),
    (9,  'Cloud Services',     'Cloud computing and hosting'),
    (10, 'Training Materials', 'Educational resources and courses')
ON CONFLICT (id) DO NOTHING;
SELECT setval('product_categories_id_seq', 10, true);

-- Products (100)
INSERT INTO products (id, name, category_id, sku, unit_price, cost_price) VALUES
    -- Electronics (15)
    (1,  'Business Laptop Pro 15',    1, 'ELEC-001', 1299.99, 850.00),
    (2,  'Business Laptop Standard',  1, 'ELEC-002', 899.99,  580.00),
    (3,  'Desktop Workstation',       1, 'ELEC-003', 1599.99, 1050.00),
    (4,  'Tablet Pro 12',             1, 'ELEC-004', 799.99,  520.00),
    (5,  'Smartphone Enterprise',     1, 'ELEC-005', 999.99,  650.00),
    (6,  'Mini PC',                   1, 'ELEC-006', 499.99,  320.00),
    (7,  'All-in-One PC',             1, 'ELEC-007', 1199.99, 780.00),
    (8,  'E-Reader Business',         1, 'ELEC-008', 249.99,  160.00),
    (9,  'Portable Projector',        1, 'ELEC-009', 599.99,  390.00),
    (10, 'Smart Display',             1, 'ELEC-010', 349.99,  220.00),
    (11, 'Conference Camera',         1, 'ELEC-011', 449.99,  290.00),
    (12, 'Wireless Presenter',        1, 'ELEC-012', 79.99,   45.00),
    (13, 'Document Scanner',          1, 'ELEC-013', 399.99,  260.00),
    (14, 'Label Printer',             1, 'ELEC-014', 199.99,  130.00),
    (15, 'UPS Battery Backup',        1, 'ELEC-015', 299.99,  195.00),
    -- Office Supplies (10)
    (16, 'Premium Paper Ream',        2, 'OFFC-001', 12.99,   6.50),
    (17, 'Executive Pen Set',         2, 'OFFC-002', 49.99,   22.00),
    (18, 'Notebook Pack (12)',         2, 'OFFC-003', 24.99,   11.00),
    (19, 'Whiteboard Markers (8)',     2, 'OFFC-004', 15.99,   7.00),
    (20, 'File Organizer',            2, 'OFFC-005', 34.99,   18.00),
    (21, 'Desk Organizer Set',        2, 'OFFC-006', 39.99,   20.00),
    (22, 'Binder Pack (10)',           2, 'OFFC-007', 29.99,   14.00),
    (23, 'Sticky Notes Bulk',          2, 'OFFC-008', 19.99,   8.50),
    (24, 'Paper Clips Assorted',       2, 'OFFC-009', 9.99,    4.00),
    (25, 'Stapler Heavy Duty',         2, 'OFFC-010', 22.99,   11.00),
    -- Furniture (10)
    (26, 'Executive Desk',            3, 'FURN-001', 699.99,  420.00),
    (27, 'Ergonomic Chair Pro',        3, 'FURN-002', 549.99,  330.00),
    (28, 'Standing Desk Converter',    3, 'FURN-003', 349.99,  210.00),
    (29, 'Conference Table 8-seat',    3, 'FURN-004', 1299.99, 780.00),
    (30, 'Bookshelf Unit',            3, 'FURN-005', 249.99,  150.00),
    (31, 'Filing Cabinet 4-drawer',    3, 'FURN-006', 199.99,  120.00),
    (32, 'Guest Chair',               3, 'FURN-007', 179.99,  108.00),
    (33, 'Sit-Stand Desk Full',        3, 'FURN-008', 899.99,  540.00),
    (34, 'Monitor Arm Dual',          3, 'FURN-009', 149.99,  90.00),
    (35, 'Desk Lamp LED',             3, 'FURN-010', 69.99,   42.00),
    -- Software Licenses (10)
    (36, 'Office Suite Annual',        4, 'SOFT-001', 299.99,  180.00),
    (37, 'Project Management Tool',    4, 'SOFT-002', 149.99,  90.00),
    (38, 'CRM Platform License',       4, 'SOFT-003', 499.99,  300.00),
    (39, 'IDE Professional',           4, 'SOFT-004', 199.99,  120.00),
    (40, 'Antivirus Enterprise',       4, 'SOFT-005', 89.99,   50.00),
    (41, 'VPN Service Annual',         4, 'SOFT-006', 79.99,   45.00),
    (42, 'Design Suite License',       4, 'SOFT-007', 599.99,  360.00),
    (43, 'Database Management',        4, 'SOFT-008', 399.99,  240.00),
    (44, 'Video Conferencing Pro',     4, 'SOFT-009', 129.99,  78.00),
    (45, 'Backup Software',           4, 'SOFT-010', 199.99,  120.00),
    -- Networking (10)
    (46, 'Enterprise Router',          5, 'NETW-001', 899.99,  540.00),
    (47, 'Managed Switch 48-port',     5, 'NETW-002', 1199.99, 720.00),
    (48, 'WiFi Access Point Pro',      5, 'NETW-003', 349.99,  210.00),
    (49, 'Network Cable Cat6 (100m)',  5, 'NETW-004', 89.99,   45.00),
    (50, 'Firewall Appliance',         5, 'NETW-005', 1499.99, 900.00),
    (51, 'Patch Panel 24-port',        5, 'NETW-006', 129.99,  78.00),
    (52, 'Network Tester',            5, 'NETW-007', 249.99,  150.00),
    (53, 'PoE Injector',              5, 'NETW-008', 59.99,   36.00),
    (54, 'Fiber Optic Cable (50m)',    5, 'NETW-009', 149.99,  90.00),
    (55, 'WiFi Range Extender',        5, 'NETW-010', 79.99,   48.00),
    -- Storage (10)
    (56, 'SSD 1TB NVMe',              6, 'STOR-001', 129.99,  78.00),
    (57, 'SSD 2TB NVMe',              6, 'STOR-002', 219.99,  132.00),
    (58, 'HDD 4TB Enterprise',        6, 'STOR-003', 149.99,  90.00),
    (59, 'External SSD 1TB',          6, 'STOR-004', 109.99,  66.00),
    (60, 'NAS 4-Bay',                 6, 'STOR-005', 599.99,  360.00),
    (61, 'USB Flash Drive 128GB',     6, 'STOR-006', 24.99,   12.00),
    (62, 'Memory Card 256GB',         6, 'STOR-007', 34.99,   18.00),
    (63, 'Tape Drive LTO',            6, 'STOR-008', 899.99,  540.00),
    (64, 'SD Card Reader',            6, 'STOR-009', 19.99,   10.00),
    (65, 'RAID Controller',           6, 'STOR-010', 449.99,  270.00),
    -- Peripherals (15)
    (66, 'Mechanical Keyboard',        7, 'PERI-001', 149.99,  90.00),
    (67, 'Wireless Mouse',            7, 'PERI-002', 69.99,   42.00),
    (68, '27" 4K Monitor',            7, 'PERI-003', 499.99,  300.00),
    (69, '32" Curved Monitor',         7, 'PERI-004', 699.99,  420.00),
    (70, 'Webcam HD 1080p',           7, 'PERI-005', 89.99,   54.00),
    (71, 'Headset Noise Cancelling',   7, 'PERI-006', 199.99,  120.00),
    (72, 'Speakerphone',              7, 'PERI-007', 149.99,  90.00),
    (73, 'USB Hub 7-port',            7, 'PERI-008', 49.99,   30.00),
    (74, 'Docking Station',           7, 'PERI-009', 249.99,  150.00),
    (75, 'Wireless Keyboard Combo',    7, 'PERI-010', 79.99,   48.00),
    (76, 'Graphics Tablet',           7, 'PERI-011', 299.99,  180.00),
    (77, 'Portable Monitor 15"',       7, 'PERI-012', 349.99,  210.00),
    (78, 'Microphone USB',            7, 'PERI-013', 129.99,  78.00),
    (79, 'Drawing Pen Display',        7, 'PERI-014', 799.99,  480.00),
    (80, 'Ergonomic Trackball',        7, 'PERI-015', 89.99,   54.00),
    -- Security (10)
    (81, 'Security Camera Indoor',     8, 'SECU-001', 199.99,  120.00),
    (82, 'Security Camera Outdoor',    8, 'SECU-002', 299.99,  180.00),
    (83, 'Access Card System',         8, 'SECU-003', 999.99,  600.00),
    (84, 'Biometric Scanner',          8, 'SECU-004', 599.99,  360.00),
    (85, 'Cable Lock Pack (10)',       8, 'SECU-005', 149.99,  90.00),
    (86, 'Privacy Screen 15"',         8, 'SECU-006', 49.99,   30.00),
    (87, 'Hardware Security Key',      8, 'SECU-007', 59.99,   36.00),
    (88, 'Safe Small',                 8, 'SECU-008', 249.99,  150.00),
    (89, 'Shredder Cross-Cut',         8, 'SECU-009', 179.99,  108.00),
    (90, 'Door Lock Smart',           8, 'SECU-010', 349.99,  210.00),
    -- Cloud Services (5)
    (91, 'Cloud Compute Basic/mo',     9, 'CLOD-001', 99.99,   60.00),
    (92, 'Cloud Compute Pro/mo',       9, 'CLOD-002', 299.99,  180.00),
    (93, 'Cloud Storage 1TB/mo',       9, 'CLOD-003', 49.99,   30.00),
    (94, 'CDN Service/mo',            9, 'CLOD-004', 79.99,   48.00),
    (95, 'Managed Database/mo',        9, 'CLOD-005', 199.99,  120.00),
    -- Training Materials (5)
    (96, 'Online Course Platform',     10, 'TRAN-001', 499.99,  300.00),
    (97, 'Technical Workshop',         10, 'TRAN-002', 299.99,  180.00),
    (98, 'Certification Prep Bundle',  10, 'TRAN-003', 199.99,  120.00),
    (99, 'Leadership Training',        10, 'TRAN-004', 399.99,  240.00),
    (100,'Safety Compliance Kit',      10, 'TRAN-005', 149.99,  90.00)
ON CONFLICT (id) DO NOTHING;
SELECT setval('products_id_seq', 100, true);

-- Customers (30)
INSERT INTO customers (id, company_name, contact_name, email, phone, city, country) VALUES
    (1,  'TechCorp International',   'James Miller',    'james@techcorp.com',     '+1-555-0101', 'San Francisco', 'USA'),
    (2,  'GlobalSoft Solutions',     'Sarah Connor',    'sarah@globalsoft.com',   '+1-555-0102', 'New York',      'USA'),
    (3,  'Nordic Digital AS',        'Erik Lindqvist',  'erik@nordicdigital.no',  '+47-555-0103', 'Oslo',          'Norway'),
    (4,  'Bayern Industries GmbH',   'Klaus Weber',     'klaus@bayern-ind.de',    '+49-555-0104', 'Munich',        'Germany'),
    (5,  'Sakura Tech Co.',          'Yuto Yamamoto',   'yuto@sakuratech.jp',     '+81-555-0105', 'Tokyo',         'Japan'),
    (6,  'Maple Leaf Computing',     'Sophie Tremblay', 'sophie@mapleleaf.ca',    '+1-555-0106', 'Toronto',       'Canada'),
    (7,  'Outback Systems Pty',      'Jack Thompson',   'jack@outback-sys.au',    '+61-555-0107', 'Sydney',        'Australia'),
    (8,  'Seine Consulting SARL',    'Marie Dubois',    'marie@seine-con.fr',     '+33-555-0108', 'Paris',         'France'),
    (9,  'Amazon Valley Tech',       'Pedro Oliveira',  'pedro@avtech.br',        '+55-555-0109', 'Sao Paulo',     'Brazil'),
    (10, 'Thames Data Ltd',          'William Harris',  'william@thamesdata.uk',  '+44-555-0110', 'London',        'UK'),
    (11, 'Alpine Innovations AG',    'Anna Huber',      'anna@alpine-inn.ch',     '+41-555-0111', 'Zurich',        'Switzerland'),
    (12, 'Ganges Software Pvt',      'Arun Nair',       'arun@gangessoft.in',     '+91-555-0112', 'Bangalore',     'India'),
    (13, 'Han River Systems',        'Min-Jun Park',    'minjun@hanriver.kr',     '+82-555-0113', 'Seoul',         'South Korea'),
    (14, 'Nile Enterprises',         'Amira Hassan',    'amira@nile-ent.eg',      '+20-555-0114', 'Cairo',         'Egypt'),
    (15, 'Pacific Rim Tech',         'David Tan',       'david@pacificrim.sg',    '+65-555-0115', 'Singapore',     'Singapore'),
    (16, 'Rocky Mountain Data',      'Mike Johnson',    'mike@rockymtn.com',      '+1-555-0116', 'Denver',        'USA'),
    (17, 'Baltic Solutions OY',      'Tuomas Virtanen', 'tuomas@baltic-sol.fi',   '+358-555-0117','Helsinki',      'Finland'),
    (18, 'Iberian Technologies SL',  'Carlos Mendez',   'carlos@iberian-tech.es', '+34-555-0118', 'Madrid',        'Spain'),
    (19, 'Great Wall Digital',       'Wei Zhang',       'wei@gwdigital.cn',       '+86-555-0119', 'Beijing',       'China'),
    (20, 'Mekong Systems Co.',       'Linh Tran',       'linh@mekongsys.vn',      '+84-555-0120', 'Ho Chi Minh',   'Vietnam'),
    (21, 'Cascade Enterprises',      'Jennifer Lee',    'jennifer@cascade.com',   '+1-555-0121', 'Seattle',       'USA'),
    (22, 'Fjord Analytics',          'Lars Olsen',      'lars@fjord-analytics.dk','+45-555-0122', 'Copenhagen',    'Denmark'),
    (23, 'Pampas Digital SA',        'Lucia Fernandez', 'lucia@pampas-dig.ar',    '+54-555-0123', 'Buenos Aires',  'Argentina'),
    (24, 'Highlands IT Services',    'Ewan MacLeod',    'ewan@highlands-it.uk',   '+44-555-0124', 'Edinburgh',     'UK'),
    (25, 'Sahara Networks',          'Omar Benali',     'omar@saharanet.ma',      '+212-555-0125','Casablanca',    'Morocco'),
    (26, 'Midwest Manufacturing',    'Tom Anderson',    'tom@midwest-mfg.com',    '+1-555-0126', 'Chicago',       'USA'),
    (27, 'Adriatic Solutions d.o.o.','Marko Novak',     'marko@adriatic-sol.hr',  '+385-555-0127','Zagreb',        'Croatia'),
    (28, 'Danube Corp Kft',         'Istvan Nagy',     'istvan@danube-corp.hu',  '+36-555-0128', 'Budapest',      'Hungary'),
    (29, 'Andes Cloud Services',     'Felipe Rojas',    'felipe@andes-cloud.cl',  '+56-555-0129', 'Santiago',      'Chile'),
    (30, 'Volga Industries',         'Alexei Volkov',   'alexei@volga-ind.ru',    '+7-555-0130',  'Moscow',        'Russia')
ON CONFLICT (id) DO NOTHING;
SELECT setval('customers_id_seq', 30, true);

-- =============================================================================
-- Orders & Order Items (generated via generate_series for realistic patterns)
-- =============================================================================

-- Generate 500 orders spanning 18 months (July 2024 - December 2025)
-- Sales employees: ids 2,15,16,17,18,19,20,46,50 (Sales dept) + some from other depts
INSERT INTO orders (id, customer_id, employee_id, order_date, ship_date, status, total_amount)
SELECT
    s.id,
    -- Cycle through customers
    ((s.id - 1) % 30) + 1 AS customer_id,
    -- Sales employees handle most orders
    CASE
        WHEN s.id % 10 < 7 THEN (ARRAY[2,15,16,17,18,19,20])[((s.id - 1) % 7) + 1]
        ELSE (ARRAY[46,50,31,32])[((s.id - 1) % 4) + 1]
    END AS employee_id,
    -- Spread across 18 months with seasonal variation
    DATE '2024-07-01' + ((s.id - 1) * 18 * 30 / 500)::integer AS order_date,
    -- Ship 2-7 days after order
    DATE '2024-07-01' + ((s.id - 1) * 18 * 30 / 500)::integer + (2 + (s.id % 6))::integer AS ship_date,
    -- Status distribution
    CASE
        WHEN s.id <= 400 THEN 'shipped'
        WHEN s.id <= 450 THEN 'delivered'
        WHEN s.id <= 480 THEN 'processing'
        ELSE 'pending'
    END AS status,
    0 AS total_amount  -- Will be updated after order_items
FROM generate_series(1, 500) AS s(id)
ON CONFLICT (id) DO NOTHING;
SELECT setval('orders_id_seq', 500, true);

-- Generate ~1500 order items (avg 3 items per order)
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, discount)
SELECT
    s.id,
    -- Each order gets 1-5 items
    ((s.id - 1) / 3) + 1 AS order_id,
    -- Varied product selection with bias toward popular categories
    CASE
        WHEN s.id % 20 < 4 THEN (s.id % 15) + 1          -- Electronics
        WHEN s.id % 20 < 7 THEN (s.id % 10) + 16         -- Office Supplies
        WHEN s.id % 20 < 9 THEN (s.id % 10) + 26         -- Furniture
        WHEN s.id % 20 < 11 THEN (s.id % 10) + 36        -- Software
        WHEN s.id % 20 < 13 THEN (s.id % 10) + 46        -- Networking
        WHEN s.id % 20 < 15 THEN (s.id % 10) + 56        -- Storage
        WHEN s.id % 20 < 17 THEN (s.id % 15) + 66        -- Peripherals
        WHEN s.id % 20 < 19 THEN (s.id % 10) + 81        -- Security
        ELSE (s.id % 5) + 91                               -- Cloud/Training
    END AS product_id,
    -- Quantity 1-10
    GREATEST(1, (s.id % 10) + 1) AS quantity,
    -- Use product's actual price (will be set correctly below)
    0 AS unit_price,
    -- Occasional discounts
    CASE WHEN s.id % 5 = 0 THEN 5.00 WHEN s.id % 7 = 0 THEN 10.00 ELSE 0.00 END AS discount
FROM generate_series(1, 1500) AS s(id)
WHERE ((s.id - 1) / 3) + 1 <= 500  -- Ensure order_id doesn't exceed 500
ON CONFLICT (id) DO NOTHING;
SELECT setval('order_items_id_seq', 1500, true);

-- Update order_items with correct unit_price from products
UPDATE order_items oi
SET unit_price = p.unit_price
FROM products p
WHERE oi.product_id = p.id AND oi.unit_price = 0;

-- Update orders total_amount from their items
UPDATE orders o
SET total_amount = sub.total
FROM (
    SELECT order_id, SUM(quantity * unit_price * (1 - discount / 100.0)) AS total
    FROM order_items
    GROUP BY order_id
) sub
WHERE o.id = sub.order_id AND o.total_amount = 0;

-- Inventory (100 products in warehouses)
INSERT INTO inventory (id, product_id, warehouse_location, quantity_on_hand, reorder_level, last_restock_date)
SELECT
    s.id,
    s.id AS product_id,
    CASE
        WHEN s.id % 3 = 0 THEN 'Warehouse-A'
        WHEN s.id % 3 = 1 THEN 'Warehouse-B'
        ELSE 'Warehouse-C'
    END AS warehouse_location,
    (50 + (s.id * 7) % 200) AS quantity_on_hand,
    (10 + (s.id * 3) % 30) AS reorder_level,
    DATE '2025-01-01' + ((s.id * 3) % 60)::integer AS last_restock_date
FROM generate_series(1, 100) AS s(id)
ON CONFLICT (id) DO NOTHING;
SELECT setval('inventory_id_seq', 100, true);

-- Projects (15)
INSERT INTO projects (id, name, department_id, lead_employee_id, start_date, end_date, budget, status) VALUES
    (1,  'Cloud Migration Phase 2',    1, 1,  '2024-06-01', '2025-06-30', 500000.00, 'active'),
    (2,  'CRM System Upgrade',         2, 2,  '2024-09-01', '2025-03-31', 250000.00, 'completed'),
    (3,  'Brand Refresh Campaign',     3, 3,  '2025-01-01', '2025-09-30', 180000.00, 'active'),
    (4,  'Employee Wellness Program',  4, 4,  '2024-07-01', '2025-12-31', 120000.00, 'active'),
    (5,  'Financial Reporting Automation', 5, 5, '2024-10-01', '2025-04-30', 200000.00, 'completed'),
    (6,  'Supply Chain Optimization',  6, 6,  '2025-03-01', '2026-02-28', 350000.00, 'active'),
    (7,  'Support Portal Redesign',    7, 7,  '2024-11-01', '2025-05-31', 150000.00, 'completed'),
    (8,  'AI Research Initiative',     8, 8,  '2024-08-01', NULL,          800000.00, 'active'),
    (9,  'Security Audit 2025',        1, 9,  '2025-01-15', '2025-04-15', 100000.00, 'completed'),
    (10, 'Sales Analytics Dashboard',  2, 15, '2025-02-01', '2025-08-31', 175000.00, 'active'),
    (11, 'DevOps Pipeline Upgrade',    1, 10, '2025-04-01', '2025-10-31', 280000.00, 'planning'),
    (12, 'Green Office Initiative',    6, 31, '2025-05-01', '2026-04-30', 90000.00,  'planning'),
    (13, 'Data Lake Architecture',     8, 39, '2024-12-01', '2025-11-30', 450000.00, 'active'),
    (14, 'Customer Retention Program', 2, 16, '2025-06-01', '2026-05-31', 200000.00, 'planning'),
    (15, 'Mobile App Development',     1, 12, '2025-07-01', NULL,          600000.00, 'planning')
ON CONFLICT (id) DO NOTHING;
SELECT setval('projects_id_seq', 15, true);

-- Project Assignments (60)
INSERT INTO project_assignments (id, project_id, employee_id, role, hours_allocated) VALUES
    -- Cloud Migration Phase 2
    (1,  1,  1,  'Project Lead',     200),
    (2,  1,  9,  'Tech Lead',        400),
    (3,  1,  11, 'Developer',        600),
    (4,  1,  12, 'Developer',        600),
    (5,  1,  45, 'Junior Developer', 500),
    -- CRM System Upgrade
    (6,  2,  2,  'Project Sponsor',  100),
    (7,  2,  15, 'Requirements Lead',300),
    (8,  2,  17, 'Business Analyst', 400),
    (9,  2,  10, 'Developer',        500),
    -- Brand Refresh Campaign
    (10, 3,  3,  'Project Lead',     300),
    (11, 3,  21, 'Creative Lead',    500),
    (12, 3,  23, 'Designer',         600),
    (13, 3,  24, 'Content Writer',   400),
    (14, 3,  48, 'Social Media',     300),
    -- Employee Wellness Program
    (15, 4,  4,  'Program Director', 200),
    (16, 4,  25, 'Coordinator',      400),
    (17, 4,  26, 'Wellness Coach',   500),
    (18, 4,  27, 'Admin Support',    300),
    -- Financial Reporting Automation
    (19, 5,  5,  'Project Lead',     200),
    (20, 5,  28, 'Lead Analyst',     500),
    (21, 5,  29, 'Data Engineer',    600),
    (22, 5,  30, 'QA Analyst',       300),
    -- Supply Chain Optimization
    (23, 6,  6,  'Project Lead',     250),
    (24, 6,  31, 'Operations Lead',  500),
    (25, 6,  33, 'Logistics Analyst',600),
    (26, 6,  34, 'Data Analyst',     400),
    (27, 6,  47, 'Implementation',   500),
    -- Support Portal Redesign
    (28, 7,  7,  'Project Lead',     200),
    (29, 7,  35, 'UX Lead',          500),
    (30, 7,  36, 'Frontend Dev',     600),
    (31, 7,  37, 'Backend Dev',      500),
    (32, 7,  38, 'QA Tester',        300),
    -- AI Research Initiative
    (33, 8,  8,  'Principal Researcher', 400),
    (34, 8,  39, 'Research Lead',    600),
    (35, 8,  40, 'Senior Researcher',600),
    (36, 8,  41, 'ML Engineer',      700),
    (37, 8,  42, 'ML Engineer',      700),
    (38, 8,  43, 'Data Scientist',   600),
    (39, 8,  44, 'Research Intern',  500),
    -- Security Audit 2025
    (40, 9,  9,  'Audit Lead',       300),
    (41, 9,  13, 'Security Analyst', 400),
    (42, 9,  14, 'Penetration Tester',300),
    -- Sales Analytics Dashboard
    (43, 10, 15, 'Product Owner',    200),
    (44, 10, 19, 'Data Analyst',     500),
    (45, 10, 20, 'Frontend Dev',     600),
    (46, 10, 46, 'Backend Dev',      500),
    -- DevOps Pipeline Upgrade
    (47, 11, 10, 'Project Lead',     300),
    (48, 11, 13, 'DevOps Engineer',  600),
    (49, 11, 49, 'Developer',        500),
    -- Green Office Initiative
    (50, 12, 31, 'Project Lead',     200),
    (51, 12, 32, 'Sustainability Lead',400),
    (52, 12, 34, 'Coordinator',      300),
    -- Data Lake Architecture
    (53, 13, 39, 'Architect',        500),
    (54, 13, 41, 'Data Engineer',    700),
    (55, 13, 43, 'Data Scientist',   500),
    -- Customer Retention Program
    (56, 14, 16, 'Program Lead',     300),
    (57, 14, 18, 'Account Manager',  400),
    (58, 14, 50, 'Data Analyst',     500),
    -- Mobile App Development
    (59, 15, 12, 'Tech Lead',        400),
    (60, 15, 45, 'Developer',        600)
ON CONFLICT (id) DO NOTHING;
SELECT setval('project_assignments_id_seq', 60, true);

-- =============================================================================
-- Verification queries (not inserted, just for checking)
-- =============================================================================
-- SELECT 'departments' AS tbl, COUNT(*) FROM departments
-- UNION ALL SELECT 'employees', COUNT(*) FROM employees
-- UNION ALL SELECT 'product_categories', COUNT(*) FROM product_categories
-- UNION ALL SELECT 'products', COUNT(*) FROM products
-- UNION ALL SELECT 'customers', COUNT(*) FROM customers
-- UNION ALL SELECT 'orders', COUNT(*) FROM orders
-- UNION ALL SELECT 'order_items', COUNT(*) FROM order_items
-- UNION ALL SELECT 'inventory', COUNT(*) FROM inventory
-- UNION ALL SELECT 'projects', COUNT(*) FROM projects
-- UNION ALL SELECT 'project_assignments', COUNT(*) FROM project_assignments;
