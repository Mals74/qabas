import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { Home as HomeIcon, Library, More, Search } from "./components/Icons.jsx";
import Home from "./pages/Home.jsx";
import LibraryPage from "./pages/Library.jsx";
import BookPage from "./pages/Book.jsx";
import LessonPage from "./pages/Lesson.jsx";
import AddLesson from "./pages/AddLesson.jsx";
import SearchPage from "./pages/Search.jsx";
import About from "./pages/About.jsx";
import FahrasPage from "./pages/Fahras.jsx";

export default function App() {
  const { pathname } = useLocation();
  return (
    <div className="app">
      <main className="screen" key={pathname}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/books/:id" element={<BookPage />} />
          <Route path="/lessons/:id" element={<LessonPage />} />
          <Route path="/add" element={<AddLesson />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/about" element={<About />} />
          <Route path="/fahras" element={<FahrasPage />} />
        </Routes>
      </main>

      {/* Bottom tab bar, right-to-left like the mockups */}
      <nav className="tabbar">
        <NavLink to="/" end><HomeIcon filled={pathname === "/"} /><span>الرئيسية</span></NavLink>
        <NavLink to="/library"><Library /><span>مكتبتي</span></NavLink>
        <NavLink to="/search"><Search /><span>البحث</span></NavLink>
        <NavLink to="/about"><More /><span>المزيد</span></NavLink>
      </nav>
    </div>
  );
}
