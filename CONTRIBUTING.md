# Contributing to ProjectCompass

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Create a virtual environment: `python -m venv venv`
4. Activate it: `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows)
5. Install dependencies: `pip install -r requirements.txt`

## Development Workflow

1. Create a feature branch: `git checkout -b feature/your-feature-name`
2. Make your changes
3. Test your changes locally
4. Commit with descriptive messages
5. Push to your fork
6. Submit a pull request

## Code Style

- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add comments for complex logic
- Keep functions focused and small

## Adding New Features

1. Extend the `ProjectCompass` class in `basefun.py`
2. Add new routes in `app.py`
3. Create corresponding HTML templates in `Templates/`
4. Update static assets in `static/` as needed
5. Update documentation

## Testing

- Test all new functionality manually
- Ensure existing features still work
- Test with different browsers for web interface

## Pull Request Guidelines

- Provide clear description of changes
- Reference any related issues
- Ensure code follows project conventions
- Update documentation if needed