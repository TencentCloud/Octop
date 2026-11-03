#!/usr/bin/env python3
"""
DDD Analyzer - Domain-Driven Design Analysis
Identifies: Aggregates, Entities, Value Objects, Domain Services, Repositories, Domain Events, Bounded Contexts
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict


# ============================================================================
# DDD Domain Models
# ============================================================================

@dataclass
class Aggregate:
    """Aggregate Root - consistency boundary"""
    name: str
    file: str
    entities: List[str] = field(default_factory=list)
    value_objects: List[str] = field(default_factory=list)
    invariants: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=list)
    repository_interface: Optional[str] = None


@dataclass
class Entity:
    """Entity - has identity and lifecycle"""
    name: str
    file: str
    identity_field: Optional[str] = None
    mutable: bool = True
    methods: List[str] = field(default_factory=list)
    aggregate_root: Optional[str] = None  # Which aggregate it belongs to


@dataclass
class ValueObject:
    """Value Object - immutable, defined by attributes"""
    name: str
    file: str
    attributes: List[str] = field(default_factory=list)
    is_immutable: bool = True
    equality_method: bool = False


@dataclass
class DomainService:
    """Domain Service - stateless business logic"""
    name: str
    file: str
    methods: List[str] = field(default_factory=list)
    operates_on: List[str] = field(default_factory=list)  # Which aggregates/entities


@dataclass
class ApplicationService:
    """Application Service - orchestration, no business logic"""
    name: str
    file: str
    use_cases: List[str] = field(default_factory=list)
    domain_services_used: List[str] = field(default_factory=list)


@dataclass
class Repository:
    """Repository - persistence abstraction"""
    name: str
    file: str
    aggregate_type: str
    methods: List[str] = field(default_factory=list)  # find, save, delete, etc.
    is_interface: bool = True


@dataclass
class DomainEvent:
    """Domain Event - something that happened"""
    name: str
    file: str
    payload_fields: List[str] = field(default_factory=list)
    publisher: Optional[str] = None
    subscribers: List[str] = field(default_factory=list)


@dataclass
class Factory:
    """Factory - complex object creation"""
    name: str
    file: str
    creates: List[str]  # What it creates
    methods: List[str] = field(default_factory=list)


@dataclass
class BoundedContext:
    """Bounded Context - boundary of domain model"""
    name: str
    directory: str
    aggregates: List[str] = field(default_factory=list)
    domain_services: List[str] = field(default_factory=list)
    ubiquitous_language: List[str] = field(default_factory=list)


@dataclass
class DDDAnalysisReport:
    """Complete DDD analysis report"""
    aggregates: List[Aggregate] = field(default_factory=list)
    entities: List[Entity] = field(default_factory=list)
    value_objects: List[ValueObject] = field(default_factory=list)
    domain_services: List[DomainService] = field(default_factory=list)
    application_services: List[ApplicationService] = field(default_factory=list)
    repositories: List[Repository] = field(default_factory=list)
    domain_events: List[DomainEvent] = field(default_factory=list)
    factories: List[Factory] = field(default_factory=list)
    bounded_contexts: List[BoundedContext] = field(default_factory=list)
    
    # Quality metrics
    aggregate_coherence: int = 0  # How well aggregates are designed
    entity_value_object_ratio: float = 0.0
    anemic_domain_risk: bool = False
    god_aggregate_warnings: List[str] = field(default_factory=list)


# ============================================================================
# DDD Analyzer
# ============================================================================

class DDDAnalyzer:
    """Analyzes codebase for DDD patterns and structures"""
    
    # DDD naming patterns
    AGGREGATE_PATTERNS = [
        r'(\w+)Aggregate',
        r'(\w+)Root',
        r'(\w+)(?:Aggregate)?(?:Root)?'  # Implicit aggregates
    ]
    
    ENTITY_PATTERNS = [
        r'(\w+)Entity',
        r'(\w+)(?:Model|Record|Item)'
    ]
    
    VALUE_OBJECT_PATTERNS = [
        r'(\w+)ValueObject',
        r'(\w+)VO',
        r'(\w+)Value',
        r'(\w+)Type',
        r'(\w+)Id',  # ID types are usually value objects
        r'(\w+)Name',
        r'(\w+)Email',
        r'(\w+)Address',
        r'(\w+)Money',
        r'(\w+)Amount'
    ]
    
    SERVICE_PATTERNS = [
        r'(\w+)DomainService',
        r'(\w+)Service',
        r'(\w+)ApplicationService',
        r'(\w+)AppService'
    ]
    
    REPOSITORY_PATTERNS = [
        r'(\w+)Repository',
        r'(\w+)Repo',
        r'(\w+)Dao',
        r'(\w+)Mapper'
    ]
    
    EVENT_PATTERNS = [
        r'(\w+)Event',
        r'(\w+)Occurred',
        r'(\w+)Created',
        r'(\w+)Updated',
        r'(\w+)Deleted'
    ]
    
    FACTORY_PATTERNS = [
        r'(\w+)Factory',
        r'(\w+)Builder',
        r'(\w+)Creator'
    ]
    
    def __init__(self, path: str):
        self.root_path = Path(path).resolve()
        self.report = DDDAnalysisReport()
        
        # Analysis state
        self.all_classes: Dict[str, Dict] = {}
        self.all_functions: Dict[str, Dict] = {}
        
    def analyze_python(self, file_path: Path, content: str, tree):
        """Analyze Python code for DDD patterns"""
        import ast
        
        rel_path = str(file_path.relative_to(self.root_path))
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                self._analyze_python_class(node, rel_path, content)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._analyze_python_function(node, rel_path, content)
    
    def _analyze_python_class(self, node: ast.ClassDef, file_path: str, content: str):
        """Analyze Python class for DDD patterns"""
        class_name = node.name
        bases = [base.id if isinstance(base, ast.Name) else str(base) for base in node.bases]
        
        # Extract methods
        methods = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(item.name)
        
        # Check for Aggregate Root
        if self._matches_pattern(class_name, self.AGGREGATE_PATTERNS) or \
           any('aggregate' in b.lower() for b in bases) or \
           self._has_aggregate_characteristics(node):
            
            aggregate = Aggregate(
                name=class_name,
                file=file_path,
                methods=methods
            )
            self._extract_aggregate_details(aggregate, node, content)
            self.report.aggregates.append(aggregate)
        
        # Check for Entity
        elif self._matches_pattern(class_name, self.ENTITY_PATTERNS) or \
             self._is_entity(node, bases):
            
            entity = Entity(
                name=class_name,
                file=file_path,
                methods=methods,
                mutable=True
            )
            self._extract_entity_details(entity, node, content)
            self.report.entities.append(entity)
        
        # Check for Value Object
        elif self._matches_pattern(class_name, self.VALUE_OBJECT_PATTERNS) or \
             self._is_value_object(node, bases):
            
            vo = ValueObject(
                name=class_name,
                file=file_path,
                attributes=self._extract_fields(node),
                is_immutable=self._is_immutable(node, content)
            )
            self.report.value_objects.append(vo)
        
        # Check for Domain Service
        elif self._matches_pattern(class_name, self.SERVICE_PATTERNS) and \
             'service' in class_name.lower():
            
            service = DomainService(
                name=class_name,
                file=file_path,
                methods=methods
            )
            self.report.domain_services.append(service)
        
        # Check for Repository
        elif self._matches_pattern(class_name, self.REPOSITORY_PATTERNS):
            
            repo = Repository(
                name=class_name,
                file=file_path,
                aggregate_type=self._infer_aggregate_type(class_name),
                methods=methods,
                is_interface=self._is_interface(node, content)
            )
            self.report.repositories.append(repo)
        
        # Check for Domain Event
        elif self._matches_pattern(class_name, self.EVENT_PATTERNS) or \
             'event' in class_name.lower():
            
            event = DomainEvent(
                name=class_name,
                file=file_path,
                payload_fields=self._extract_fields(node)
            )
            self.report.domain_events.append(event)
        
        # Check for Factory
        elif self._matches_pattern(class_name, self.FACTORY_PATTERNS):
            
            factory = Factory(
                name=class_name,
                file=file_path,
                creates=[],
                methods=methods
            )
            self.report.factories.append(factory)
    
    def _analyze_python_function(self, node: ast.FunctionDef, file_path: str, content: str):
        """Analyze function for DDD patterns"""
        func_name = node.name
        
        # Application services often have names like create_x, update_x, handle_x
        if any(func_name.startswith(prefix) for prefix in ['create', 'update', 'delete', 'handle', 'process']):
            # Check if it's in a service class
            pass  # Would need parent context
    
    def analyze_rust(self, file_path: Path, content: str):
        """Analyze Rust code for DDD patterns"""
        rel_path = str(file_path.relative_to(self.root_path))
        
        # Extract structs
        struct_pattern = r'(?:pub\s+)?struct\s+(\w+)'
        for match in re.finditer(struct_pattern, content):
            name = match.group(1)
            
            # Check patterns
            if self._matches_pattern(name, self.AGGREGATE_PATTERNS):
                self.report.aggregates.append(Aggregate(name=name, file=rel_path))
            elif self._matches_pattern(name, self.VALUE_OBJECT_PATTERNS):
                self.report.value_objects.append(ValueObject(name=name, file=rel_path))
            elif self._matches_pattern(name, self.EVENT_PATTERNS):
                self.report.domain_events.append(DomainEvent(name=name, file=rel_path))
        
        # Extract traits (interfaces)
        trait_pattern = r'(?:pub\s+)?trait\s+(\w+)'
        for match in re.finditer(trait_pattern, content):
            name = match.group(1)
            if 'Repository' in name or 'Repo' in name:
                self.report.repositories.append(
                    Repository(name=name, file=rel_path, aggregate_type=self._infer_aggregate_type(name))
                )
    
    def analyze_typescript(self, file_path: Path, content: str):
        """Analyze TypeScript code for DDD patterns"""
        rel_path = str(file_path.relative_to(self.root_path))
        
        # Extract classes and interfaces
        class_pattern = r'(?:export\s+)?(?:abstract\s+)?(?:class|interface)\s+(\w+)'
        for match in re.finditer(class_pattern, content):
            name = match.group(1)
            
            if self._matches_pattern(name, self.AGGREGATE_PATTERNS):
                self.report.aggregates.append(Aggregate(name=name, file=rel_path))
            elif self._matches_pattern(name, self.ENTITY_PATTERNS):
                self.report.entities.append(Entity(name=name, file=rel_path))
            elif self._matches_pattern(name, self.VALUE_OBJECT_PATTERNS):
                self.report.value_objects.append(ValueObject(name=name, file=rel_path))
            elif self._matches_pattern(name, self.EVENT_PATTERNS):
                self.report.domain_events.append(DomainEvent(name=name, file=rel_path))
    
    def identify_bounded_contexts(self):
        """Identify bounded contexts from directory structure"""
        dir_structure = defaultdict(list)
        
        # Group by top-level directory
        for agg in self.report.aggregates:
            parts = agg.file.split('/')
            if len(parts) > 1:
                dir_structure[parts[0]].append(agg.name)
        
        for ctx_name, aggregates in dir_structure.items():
            if aggregates:
                self.report.bounded_contexts.append(
                    BoundedContext(
                        name=ctx_name.title().replace('_', ' '),
                        directory=ctx_name,
                        aggregates=aggregates
                    )
                )
    
    def calculate_quality_metrics(self):
        """Calculate DDD quality metrics"""
        report = self.report
        
        # Entity vs Value Object ratio
        if report.entities:
            report.entity_value_object_ratio = len(report.value_objects) / len(report.entities)
        
        # Aggregate coherence (simplified)
        if report.aggregates:
            avg_entities_per_agg = sum(len(a.entities) for a in report.aggregates) / len(report.aggregates)
            # Good aggregates have 2-5 entities
            if 2 <= avg_entities_per_agg <= 5:
                report.aggregate_coherence = 80
            elif avg_entities_per_agg < 2:
                report.aggregate_coherence = 60  # Might be too simple
            else:
                report.aggregate_coherence = 40  # Too complex
                report.god_aggregate_warnings.append("Some aggregates may be too large")
        
        # Anemic domain model detection
        if report.aggregates and report.entities:
            total_methods = sum(len(a.methods) for a in report.aggregates) + \
                          sum(len(e.methods) for e in report.entities)
            avg_methods = total_methods / (len(report.aggregates) + len(report.entities))
            
            if avg_methods < 3:
                report.anemic_domain_risk = True
    
    def export_report(self, output_path: str):
        """Export DDD analysis report"""
        report = self.report
        
        md = []
        md.append("# 🏗️ DDD Analysis Report\n")
        md.append(f"**Path:** {self.root_path}\n")
        
        # Summary
        md.append("## 📊 Summary\n")
        md.append(f"- **Aggregates:** {len(report.aggregates)}")
        md.append(f"- **Entities:** {len(report.entities)}")
        md.append(f"- **Value Objects:** {len(report.value_objects)}")
        md.append(f"- **Domain Services:** {len(report.domain_services)}")
        md.append(f"- **Repositories:** {len(report.repositories)}")
        md.append(f"- **Domain Events:** {len(report.domain_events)}")
        md.append(f"- **Bounded Contexts:** {len(report.bounded_contexts)}\n")
        
        # Quality Metrics
        self.calculate_quality_metrics()
        md.append("\n## 📈 Quality Metrics\n")
        md.append(f"- **Aggregate Coherence:** {report.aggregate_coherence}/100")
        md.append(f"- **Entity/VO Ratio:** {report.entity_value_object_ratio:.2f}")
        md.append(f"- **Anemic Domain Risk:** {'⚠️ Yes' if report.anemic_domain_risk else '✅ No'}")
        
        if report.god_aggregate_warnings:
            md.append("\n### ⚠️ Warnings\n")
            for warning in report.god_aggregate_warnings:
                md.append(f"- {warning}")
        
        # Bounded Contexts
        if report.bounded_contexts:
            md.append("\n## 🗺️ Bounded Contexts\n")
            for ctx in report.bounded_contexts:
                md.append(f"\n### {ctx.name}\n")
                md.append(f"**Directory:** `{ctx.directory}/`\n")
                md.append("**Aggregates:**\n")
                for agg in ctx.aggregates:
                    md.append(f"- {agg}")
        
        # Aggregates
        if report.aggregates:
            md.append("\n## 🎯 Aggregates\n")
            for agg in report.aggregates:
                md.append(f"\n### {agg.name}\n")
                md.append(f"- **File:** `{agg.file}`")
                if agg.entities:
                    md.append(f"- **Entities:** {', '.join(agg.entities)}")
                if agg.value_objects:
                    md.append(f"- **Value Objects:** {', '.join(agg.value_objects)}")
                if agg.invariants:
                    md.append(f"- **Invariants:** {len(agg.invariants)}")
                if agg.methods:
                    md.append(f"- **Methods:** {', '.join(agg.methods[:10])}")
                    if len(agg.methods) > 10:
                        md.append(f"  ... and {len(agg.methods) - 10} more")
        
        # Entities
        if report.entities:
            md.append("\n## 📦 Entities\n")
            for entity in report.entities[:20]:
                md.append(f"\n**{entity.name}** (`{entity.file}`)\n")
                if entity.identity_field:
                    md.append(f"- Identity: `{entity.identity_field}`")
                if entity.methods:
                    md.append(f"- Methods: {', '.join(entity.methods[:5])}")
        
        # Value Objects
        if report.value_objects:
            md.append("\n## 💎 Value Objects\n")
            for vo in report.value_objects[:20]:
                md.append(f"\n**{vo.name}** (`{vo.file}`)\n")
                md.append(f"- Immutable: {'✅ Yes' if vo.is_immutable else '❌ No'}")
                if vo.attributes:
                    md.append(f"- Attributes: {', '.join(vo.attributes[:5])}")
        
        # Domain Services
        if report.domain_services:
            md.append("\n## ⚙️ Domain Services\n")
            for service in report.domain_services[:10]:
                md.append(f"\n**{service.name}** (`{service.file}`)\n")
                if service.methods:
                    md.append(f"- Methods: {', '.join(service.methods[:5])}")
        
        # Repositories
        if report.repositories:
            md.append("\n## 🗄️ Repositories\n")
            for repo in report.repositories[:10]:
                md.append(f"\n**{repo.name}** (`{repo.file}`)\n")
                md.append(f"- Aggregate: {repo.aggregate_type}")
                md.append(f"- Interface: {'✅ Yes' if repo.is_interface else '❌ No'}")
                if repo.methods:
                    md.append(f"- Methods: {', '.join(repo.methods[:5])}")
        
        # Domain Events
        if report.domain_events:
            md.append("\n## 📢 Domain Events\n")
            for event in report.domain_events[:15]:
                md.append(f"\n**{event.name}** (`{event.file}`)\n")
                if event.payload_fields:
                    md.append(f"- Payload: {', '.join(event.payload_fields[:5])}")
        
        # Recommendations
        md.append("\n## 💡 Recommendations\n")
        
        if report.anemic_domain_risk:
            md.append("\n### ⚠️ Anemic Domain Model Detected\n")
            md.append("Your aggregates/entities have few methods. Consider:\n")
            md.append("1. Moving business logic from services to aggregates")
            md.append("2. Adding behavior methods to entities")
            md.append("3. Using rich domain model pattern")
        
        if report.aggregate_coherence < 60:
            md.append("\n### ⚠️ Aggregate Design Issues\n")
            md.append("Consider:\n")
            md.append("1. Reviewing aggregate boundaries")
            md.append("2. Splitting large aggregates")
            md.append("3. Ensuring each aggregate has clear responsibility")
        
        if report.entity_value_object_ratio > 3:
            md.append("\n### ℹ️ Consider More Value Objects\n")
            md.append("You have many more entities than value objects. ")
            md.append("Consider using value objects for:\n")
            md.append("- IDs, names, emails, addresses")
            md.append("- Money, amounts, quantities")
            md.append("- Other immutable concepts")
        
        # Write file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md))
    
    # Helper methods
    def _matches_pattern(self, name: str, patterns: List[str]) -> bool:
        """Check if name matches any pattern"""
        for pattern in patterns:
            if re.search(pattern, name, re.IGNORECASE):
                return True
        return False
    
    def _has_aggregate_characteristics(self, node) -> bool:
        """Check if class has aggregate characteristics"""
        # Has multiple entities/value objects as fields
        # Has invariants
        # Has business logic methods
        return False  # Simplified
    
    def _is_entity(self, node, bases: List[str]) -> bool:
        """Check if class is an entity"""
        return any('entity' in b.lower() for b in bases)
    
    def _is_value_object(self, node, bases: List[str]) -> bool:
        """Check if class is a value object"""
        return any('value' in b.lower() or 'vo' in b.lower() for b in bases)
    
    def _extract_fields(self, node) -> List[str]:
        """Extract field names from class"""
        fields = []
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                fields.append(item.target.id)
        return fields
    
    def _is_immutable(self, node, content: str) -> bool:
        """Check if class is immutable"""
        # Look for @dataclass(frozen=True) or similar
        return '@dataclass(frozen=True)' in content or 'frozen=True' in content
    
    def _is_interface(self, node, content: str) -> bool:
        """Check if class is an interface/abstract"""
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.body and \
               isinstance(item.body[0], ast.Pass):
                return True
        return False
    
    def _infer_aggregate_type(self, repo_name: str) -> str:
        """Infer which aggregate a repository is for"""
        # Remove Repository/Repo suffix
        for suffix in ['Repository', 'Repo', 'Dao', 'Mapper']:
            if repo_name.endswith(suffix):
                return repo_name[:-len(suffix)]
        return repo_name
    
    def _extract_aggregate_details(self, aggregate: Aggregate, node, content: str):
        """Extract detailed information about aggregate"""
        # Implementation would analyze class structure
        pass
    
    def _extract_entity_details(self, entity: Entity, node, content: str):
        """Extract detailed information about entity"""
        # Find identity field (id, uuid, etc.)
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                if item.target.id in ['id', 'uuid', 'entity_id']:
                    entity.identity_field = item.target.id


# ============================================================================
# Main
# ============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='DDD Analyzer')
    parser.add_argument('--path', '-p', default='.', help='Path to codebase')
    parser.add_argument('--output', '-o', help='Output file')
    
    args = parser.parse_args()
    
    analyzer = DDDAnalyzer(args.path)
    # Run analysis (would integrate with main analyzer)
    
    if args.output:
        analyzer.export_report(args.output)
        print(f"DDD report saved to: {args.output}")


if __name__ == '__main__':
    main()
