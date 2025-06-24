interface TechItemProps {
  title: string
  description: string
}

export default function About() {
  return (
    <div className="max-w-3xl mx-auto">
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold mb-4 text-foreground">About Us</h1>
        <p className="text-xl text-muted-foreground">
          This is a modern full-stack application built with cutting-edge technologies
        </p>
      </div>

      <div className="bg-card text-card-foreground rounded-lg shadow-sm p-8 mb-8">
        <h2 className="text-2xl font-semibold mb-6 text-card-foreground">Tech Stack</h2>
        <ul className="space-y-4">
          <TechItem
            title="React 19"
            description="Latest React features including modern patterns and optimizations"
          />
          <TechItem
            title="FastAPI"
            description="Modern, fast web framework for building APIs with Python"
          />
          <TechItem
            title="TailwindCSS"
            description="Utility-first CSS framework with dark mode support"
          />
          <TechItem
            title="React Router 7"
            description="Latest routing capabilities with data loading and code splitting"
          />
        </ul>
      </div>

      <div className="bg-card text-card-foreground rounded-lg shadow-sm p-8">
        <h2 className="text-2xl font-semibold mb-6 text-card-foreground">Project Goals</h2>
        <ul className="list-disc list-inside space-y-3 text-muted-foreground">
          <li>Demonstrate modern full-stack development practices</li>
          <li>Provide a solid foundation for building production applications</li>
          <li>Showcase the latest features from React and FastAPI</li>
          <li>Implement responsive design with dark mode support</li>
        </ul>
      </div>
    </div>
  )
}

function TechItem({ title, description }: TechItemProps) {
  return (
    <li className="flex items-start space-x-4 p-4 rounded-lg bg-muted/50">
      <div className="flex-1">
        <h3 className="font-semibold text-card-foreground">{title}</h3>
        <p className="text-muted-foreground">{description}</p>
      </div>
    </li>
  )
}
