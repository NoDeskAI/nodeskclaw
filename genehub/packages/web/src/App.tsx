import { BrowserRouter, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import Browse from './pages/Browse';
import GeneDetail from './pages/GeneDetail';
import GenomeBrowse from './pages/GenomeBrowse';
import GenomeDetail from './pages/GenomeDetail';
import Home from './pages/Home';
import Settings from './pages/Settings';
import TemplateBrowse from './pages/TemplateBrowse';
import TemplateDetail from './pages/TemplateDetail';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="browse" element={<Browse />} />
          <Route path="genes/:slug" element={<GeneDetail />} />
          <Route path="genomes" element={<GenomeBrowse />} />
          <Route path="genomes/:slug" element={<GenomeDetail />} />
          <Route path="templates" element={<TemplateBrowse />} />
          <Route path="templates/:slug" element={<TemplateDetail />} />
          <Route path="settings/keys" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
