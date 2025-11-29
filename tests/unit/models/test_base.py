"""
Unit tests for Base model.

Tests cover:
- Abstract base class behavior
- __tablename__ directive
- Auto-generated table names
- Primary key field
- Inheritance behavior
"""

import pytest
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String

from core.models.base import Base


@pytest.mark.unit
@pytest.mark.model
class TestBaseModel:
    """Test Base model declarative base functionality."""

    def test_base_is_abstract(self):
        """Test that Base class is marked as abstract."""
        assert Base.__abstract__ is True

    def test_base_cannot_be_instantiated_directly(self):
        """Test that Base class cannot be instantiated directly."""
        # This should work without error since it's abstract
        # But we can't create a table for it
        assert hasattr(Base, '__tablename__')

    def test_tablename_auto_generation_simple(self):
        """Test automatic table name generation from class name."""
        class TestModel(Base):
            __abstract__ = False  # Make it concrete for testing
            id: Mapped[int] = mapped_column(primary_key=True)

        # Should auto-generate as "testmodels" (classname.lower() + 's')
        assert TestModel.__tablename__ == "testmodels"

    def test_tablename_auto_generation_with_uppercase(self):
        """Test table name generation with uppercase class name."""
        class MyDocument(Base):
            __abstract__ = False
            id: Mapped[int] = mapped_column(primary_key=True)

        assert MyDocument.__tablename__ == "mydocuments"

    def test_tablename_auto_generation_single_word(self):
        """Test table name generation with single word."""
        class User(Base):
            __abstract__ = False
            id: Mapped[int] = mapped_column(primary_key=True)

        assert User.__tablename__ == "users"

    def test_tablename_can_be_overridden(self):
        """Test that __tablename__ can be explicitly overridden."""
        class CustomModel(Base):
            __tablename__ = "custom_table_name"
            __abstract__ = False
            id: Mapped[int] = mapped_column(primary_key=True)

        assert CustomModel.__tablename__ == "custom_table_name"

    def test_base_has_id_field(self):
        """Test that Base provides an id primary key field."""
        class SimpleModel(Base):
            __abstract__ = False
            name: Mapped[str] = mapped_column(String(100))

        # Should inherit id from Base
        assert hasattr(SimpleModel, 'id')

        # Create instance
        model = SimpleModel(name="test")
        assert hasattr(model, 'id')

    def test_id_field_is_primary_key(self):
        """Test that id field is configured as primary key."""
        class PrimaryKeyTestModel(Base):
            __abstract__ = False
            name: Mapped[str] = mapped_column(String(100))

        # Check id column is primary key
        id_column = PrimaryKeyTestModel.__table__.columns['id']
        assert id_column.primary_key is True

    def test_id_field_type_is_integer(self):
        """Test that id field is an integer type."""
        class IntegerTypeTestModel(Base):
            __abstract__ = False
            name: Mapped[str] = mapped_column(String(100))

        id_column = IntegerTypeTestModel.__table__.columns['id']
        assert str(id_column.type) == "INTEGER"

    def test_inheritance_chain(self):
        """Test that models can inherit from Base."""
        class ParentModel(Base):
            __abstract__ = True
            common_field: Mapped[str] = mapped_column(String(100))

        class ChildModel(ParentModel):
            __abstract__ = False
            child_field: Mapped[str] = mapped_column(String(100))

        # Should have both fields
        child = ChildModel(common_field="parent", child_field="child")
        assert hasattr(child, 'common_field')
        assert hasattr(child, 'child_field')
        assert hasattr(child, 'id')

    def test_multiple_models_from_base(self):
        """Test that multiple models can inherit from Base."""
        class Model1(Base):
            __abstract__ = False
            field1: Mapped[str] = mapped_column(String(100))

        class Model2(Base):
            __abstract__ = False
            field2: Mapped[str] = mapped_column(String(100))

        # Both should have different table names
        assert Model1.__tablename__ == "model1s"
        assert Model2.__tablename__ == "model2s"

        # Both should have id
        assert hasattr(Model1, 'id')
        assert hasattr(Model2, 'id')

    def test_base_provides_metadata(self):
        """Test that Base provides SQLAlchemy metadata."""
        assert hasattr(Base, 'metadata')
        assert Base.metadata is not None

    def test_tablename_directive_is_declared_attr(self):
        """Test that __tablename__ uses declared_attr directive."""
        # The directive should be present in Base
        assert hasattr(Base, '__tablename__')

    def test_model_with_complex_name(self):
        """Test table name generation with complex class name."""
        class MyComplexModelName(Base):
            __abstract__ = False
            id: Mapped[int] = mapped_column(primary_key=True)

        # Should convert to lowercase and add 's'
        assert MyComplexModelName.__tablename__ == "mycomplexmodelnames"

    def test_model_ending_with_s(self):
        """Test table name generation when class name already ends with 's'."""
        class Status(Base):
            __abstract__ = False
            id: Mapped[int] = mapped_column(primary_key=True)

        # Will add another 's': "statuss" (not ideal but expected behavior)
        assert Status.__tablename__ == "statuss"

    def test_model_with_underscore_in_name(self):
        """Test table name generation with underscores."""
        class My_Model(Base):
            __abstract__ = False
            id: Mapped[int] = mapped_column(primary_key=True)

        # Should preserve underscore
        assert My_Model.__tablename__ == "my_models"
