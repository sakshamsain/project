import Link from "next/link";
import Masthead from "@/components/Masthead";
import CompanySearch from "@/components/CompanySearch";

export const metadata = { title: "Find a company" };

export default function Search() {
  return (
    <main className="page">
      <Masthead note="Find a company" />
      <CompanySearch />
    </main>
  );
}
