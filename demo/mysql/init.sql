-- Demo HR: departments, employees, projects

CREATE TABLE departments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    location VARCHAR(80) NOT NULL,
    budget DECIMAL(12,2) NOT NULL
);

CREATE TABLE employees (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    department_id INT,
    position VARCHAR(80) NOT NULL,
    salary DECIMAL(10,2) NOT NULL,
    hire_date DATE NOT NULL,
    FOREIGN KEY (department_id) REFERENCES departments(id)
);

CREATE TABLE projects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    department_id INT,
    status ENUM('planning','active','completed','on_hold') NOT NULL DEFAULT 'planning',
    start_date DATE NOT NULL,
    end_date DATE,
    FOREIGN KEY (department_id) REFERENCES departments(id)
);

INSERT INTO departments (name, location, budget) VALUES
('Engineering', 'Milan', 1200000.00),
('Marketing', 'Rome', 800000.00),
('Sales', 'London', 950000.00),
('Human Resources', 'Milan', 400000.00),
('Finance', 'Frankfurt', 600000.00),
('Product', 'Barcelona', 700000.00);

INSERT INTO employees (name, department_id, position, salary, hire_date) VALUES
('Marco Verdi', 1, 'Senior Engineer', 72000.00, '2019-03-15'),
('Sara Conti', 1, 'Staff Engineer', 95000.00, '2017-06-01'),
('Paolo Neri', 1, 'Junior Engineer', 45000.00, '2024-01-10'),
('Anna Russo', 2, 'Marketing Manager', 68000.00, '2020-09-01'),
('Luca Moretti', 2, 'Content Specialist', 42000.00, '2023-02-20'),
('Emma Fischer', 3, 'Sales Director', 88000.00, '2018-11-01'),
('Thomas Braun', 3, 'Account Executive', 55000.00, '2021-07-15'),
('Maria Lopez', 3, 'Account Executive', 53000.00, '2022-03-10'),
('Clara Schmidt', 4, 'HR Manager', 62000.00, '2019-01-20'),
('Yuki Sato', 4, 'Recruiter', 40000.00, '2024-06-01'),
('Pierre Dupont', 5, 'Finance Controller', 75000.00, '2018-04-01'),
('Sofia Lindgren', 5, 'Accountant', 48000.00, '2023-09-15'),
('Andrea Bianchi', 6, 'Product Manager', 78000.00, '2020-01-10'),
('Lisa Eriksson', 6, 'UX Designer', 58000.00, '2021-05-20'),
('Raj Patel', 1, 'DevOps Engineer', 70000.00, '2022-08-01'),
('Nina Kowalski', 2, 'Social Media Manager', 44000.00, '2024-03-01'),
('James Wilson', 3, 'Sales Representative', 46000.00, '2023-11-15'),
('Olga Ivanova', 1, 'Data Engineer', 68000.00, '2021-02-01');

INSERT INTO projects (name, department_id, status, start_date, end_date) VALUES
('Platform Redesign', 1, 'active', '2025-01-15', NULL),
('Mobile App v3', 1, 'active', '2025-03-01', NULL),
('Brand Refresh Campaign', 2, 'completed', '2024-09-01', '2025-02-28'),
('Q2 Lead Generation', 2, 'active', '2025-04-01', NULL),
('EMEA Expansion', 3, 'active', '2025-02-01', NULL),
('Partner Portal', 3, 'planning', '2025-07-01', NULL),
('Employee Wellness Program', 4, 'active', '2025-01-01', NULL),
('Annual Budget Review', 5, 'completed', '2024-11-01', '2025-01-31'),
('Cost Optimization', 5, 'active', '2025-03-15', NULL),
('New Feature Discovery', 6, 'active', '2025-02-15', NULL),
('Data Pipeline Migration', 1, 'on_hold', '2025-05-01', NULL),
('Customer Onboarding Flow', 6, 'planning', '2025-08-01', NULL);
