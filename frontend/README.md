# Ultimate PDF Frontend

A comprehensive React/Next.js frontend application for the Ultimate PDF processing platform, providing advanced PDF redaction, splitting, merging, and extraction capabilities.

## 🚀 Features

- **Advanced PDF Processing**: Redaction, splitting, merging, and data extraction
- **Real-time Upload**: Drag-and-drop file upload with progress tracking
- **PDF Viewer**: Interactive PDF viewing with zoom, navigation, and search
- **Session Management**: Secure 8-hour sessions with automatic cleanup
- **Responsive Design**: Mobile-first design with Tailwind CSS
- **Type Safety**: Full TypeScript support with strict mode
- **State Management**: Zustand for predictable state management
- **Testing**: Comprehensive test coverage with Jest and React Testing Library

## 📋 Prerequisites

- Node.js 18.0.0 or higher
- npm 8.0.0 or higher
- Ultimate PDF Django backend running on localhost:8000

## 🔧 Installation

1. **Clone the repository and navigate to the frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Set up environment variables:**
   ```bash
   cp .env.local.example .env.local
   ```
   
   Edit `.env.local` with your configuration:
   ```bash
   NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
   NEXT_PUBLIC_MAX_FILE_SIZE=104857600
   NEXT_PUBLIC_UPLOAD_TIMEOUT=300000
   NEXT_PUBLIC_SESSION_TIMEOUT=28800000
   ```

## 🏃‍♂️ Development

**Start the development server:**
```bash
npm run dev
```

The application will be available at `http://localhost:3000`.

**Other development commands:**
```bash
# Type checking
npm run type-check

# Linting
npm run lint
npm run lint:fix

# Testing
npm test
npm run test:watch
npm run test:coverage
```

## 🏗️ Build

**Build for production:**
```bash
npm run build
```

**Start production server:**
```bash
npm start
```

## 📁 Project Structure

```
frontend/
├── src/
│   ├── app/                    # Next.js App Router
│   │   ├── globals.css        # Global styles and Tailwind imports
│   │   ├── layout.tsx         # Root layout component
│   │   └── page.tsx           # Homepage component
│   ├── components/            # React components
│   │   ├── ErrorBoundary.tsx  # Error boundary component
│   │   ├── FileUpload.tsx     # File upload with drag-and-drop
│   │   ├── LoadingSpinner.tsx # Loading spinner component
│   │   ├── PDFViewer.tsx      # PDF viewing component
│   │   └── ProgressBar.tsx    # Progress bar component
│   ├── services/              # API communication
│   │   ├── api.ts            # Base API service
│   │   └── pdfService.ts     # PDF-specific API calls
│   ├── store/                 # Zustand state management
│   │   ├── index.ts          # Store exports
│   │   └── pdfStore.ts       # Main PDF store
│   ├── types/                 # TypeScript type definitions
│   │   └── index.ts          # All type definitions
│   ├── utils/                 # Utility functions
│   │   ├── fileUtils.ts      # File handling utilities
│   │   ├── formatUtils.ts    # Formatting utilities
│   │   └── sessionUtils.ts   # Session management
│   └── __tests__/            # Test files
│       ├── components/       # Component tests
│       ├── services/         # Service tests
│       └── store/           # Store tests
├── public/                   # Static assets
├── .env.local.example       # Environment variables template
├── .eslintrc.json          # ESLint configuration
├── .gitignore              # Git ignore rules
├── .prettierrc             # Prettier configuration
├── jest.config.js          # Jest test configuration
├── next.config.js          # Next.js configuration
├── package.json            # Dependencies and scripts
├── postcss.config.js       # PostCSS configuration
├── tailwind.config.js      # Tailwind CSS configuration
└── tsconfig.json           # TypeScript configuration
```

## 🧪 Testing

The project uses Jest and React Testing Library for comprehensive testing:

**Run tests:**
```bash
# Run all tests
npm test

# Run tests in watch mode
npm run test:watch

# Run tests with coverage report
npm run test:coverage
```

**Test coverage requirements:**
- Minimum 80% coverage for branches, functions, lines, and statements
- All components must have corresponding test files
- All services must have comprehensive API mocking

**Testing utilities:**
- Custom matchers for validation testing
- Comprehensive mocking setup for external dependencies
- Accessibility testing with jest-dom

## 🎨 Styling

The project uses **Tailwind CSS** for styling with:

- **Design System**: Custom color palette and spacing scale
- **Components**: Reusable UI component classes
- **Responsive Design**: Mobile-first responsive utilities
- **Dark Mode**: Ready for dark mode implementation
- **Animations**: Custom animations for PDF processing states

**Key styling features:**
- PDF-specific shadow and layout utilities
- Drag-and-drop visual feedback
- Progress bar animations
- Loading state transitions

## 📚 API Integration

The frontend integrates with the Django backend through:

### **API Services Structure**
- `api.ts`: Base API configuration with Axios
- `pdfService.ts`: PDF-specific operations

### **Supported Operations**
- File upload with progress tracking
- PDF redaction with match preview/approval
- PDF splitting by page ranges, bookmarks, or patterns
- PDF merging with bookmark preservation
- Data extraction (text, images, tables, metadata)
- Session management and cleanup

### **Error Handling**
- Automatic retry for transient errors
- Comprehensive error categorization
- User-friendly error messages
- Network failure resilience

## 🔐 Security Features

- **File Validation**: Comprehensive PDF file validation
- **Session Security**: 8-hour session timeout with warnings
- **CSRF Protection**: Automatic CSRF token handling
- **Input Sanitization**: All user inputs are sanitized
- **Error Logging**: Secure error reporting without sensitive data

## ♿ Accessibility

The application follows WCAG 2.1 guidelines:

- **Keyboard Navigation**: Full keyboard accessibility
- **Screen Reader Support**: ARIA labels and semantic HTML
- **Color Contrast**: WCAG AA compliant color scheme
- **Focus Management**: Visible focus indicators
- **Alternative Text**: Comprehensive alt text for images

## 🚀 Performance

**Optimization features:**
- **Code Splitting**: Automatic route-based code splitting
- **Image Optimization**: Next.js automatic image optimization
- **Bundle Analysis**: Built-in bundle analyzer
- **Caching**: Intelligent API response caching
- **Lazy Loading**: Component lazy loading where appropriate

## 🔧 Configuration

### **Environment Variables**
| Variable | Description | Default |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_BASE_URL` | Django backend API URL | `http://localhost:8000/api` |
| `NEXT_PUBLIC_MAX_FILE_SIZE` | Maximum upload file size (bytes) | `104857600` (100MB) |
| `NEXT_PUBLIC_UPLOAD_TIMEOUT` | Upload timeout (milliseconds) | `300000` (5 minutes) |
| `NEXT_PUBLIC_SESSION_TIMEOUT` | Session timeout (milliseconds) | `28800000` (8 hours) |

### **TypeScript Configuration**
- **Strict Mode**: Enabled with comprehensive type checking
- **Path Mapping**: Clean imports using `@/` prefix
- **No 'any' Types**: Enforced strict typing

### **ESLint Rules**
- **TypeScript**: Strict TypeScript rules
- **React**: React Hooks and JSX best practices
- **Accessibility**: jsx-a11y rules for accessibility
- **Import Organization**: Consistent import ordering

## 🐛 Troubleshooting

### **Common Issues**

**Upload fails with "Network Error":**
- Verify Django backend is running on `localhost:8000`
- Check CORS settings in Django backend
- Verify file size is under 100MB limit

**PDF viewer doesn't load:**
- Ensure PDF.js worker is properly configured
- Check browser console for PDF parsing errors
- Verify PDF file is not corrupted

**Session expires unexpectedly:**
- Check session timeout settings
- Verify backend session management is working
- Clear localStorage and restart application

**TypeScript errors:**
- Run `npm run type-check` for detailed errors
- Ensure all imports use proper TypeScript types
- Check for missing type definitions

### **Development Tips**

**Hot Reloading Issues:**
```bash
# Clear Next.js cache
rm -rf .next
npm run dev
```

**Test Coverage Issues:**
```bash
# Generate detailed coverage report
npm run test:coverage -- --verbose
```

**API Integration Issues:**
```bash
# Enable API debugging
NEXT_PUBLIC_ENABLE_DEBUG=true npm run dev
```

## 📈 Deployment

### **Production Build**
```bash
# Create optimized production build
npm run build

# Test production build locally
npm start
```

### **Deployment Checklist**
- [ ] Set production environment variables
- [ ] Configure proper API base URL
- [ ] Enable analytics if required
- [ ] Test file upload functionality
- [ ] Verify PDF processing workflows
- [ ] Check responsive design on different devices
- [ ] Test accessibility features
- [ ] Validate performance metrics

## 🤝 Contributing

1. **Follow the established patterns:**
   - Use TypeScript strict mode
   - Follow ESLint and Prettier rules
   - Write comprehensive tests
   - Use semantic HTML

2. **Component development:**
   - One component per file
   - Include prop interfaces
   - Add accessibility attributes
   - Write corresponding tests

3. **State management:**
   - Use Zustand for global state
   - Follow the established store structure
   - Include proper error handling
   - Add loading states

## 📄 License

This project is part of the Ultimate PDF processing platform. See the main project LICENSE file for details.

---

**🔗 Related Documentation:**
- [Ultimate PDF Backend API](../backend/README.md)
- [Project Overview](../README.md)
- [Django Backend Documentation](../backend/docs/)

For questions or support, please refer to the main project documentation or create an issue in the project repository.